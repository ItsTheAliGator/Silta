from __future__ import annotations

import contextlib
import json
import re
import socket
import threading
import time
from typing import Any, Dict, Optional, Tuple
import sys

from .cursor import CursorAdapter
from .keys import OPPOSITE_EDGE, format_key
from .local_cursor import LocalCursorManager
from .protocol import ProtocolError, build_client_hello, validate_server_welcome
from .utils import LOG, ConnectionError, import_pyautogui, import_pynput, json_dumps

if sys.platform == "darwin":
    DEFAULT_TOGGLE_HOTKEY = "<cmd>+<option>+f"
    DEFAULT_BACK_HOTKEY = "<cmd>+<option>+d"
else:
    DEFAULT_TOGGLE_HOTKEY = "<ctrl>+<alt>+f"
    DEFAULT_BACK_HOTKEY = "<ctrl>+<alt>+d"


ServerTarget = Tuple[str, int, Optional[str]]


class _MacButton:
    def __init__(self, name: str) -> None:
        self.name = name


class FlowClient:
    def __init__(
        self,
        server_host: str,
        server_port: int,
        token: Optional[str],
        edge: Optional[str],
        edge_margin: int,
        edge_delay: float,
        toggle_hotkey: str,
        back_hotkey: str,
        heartbeat: float,
        local_cursor_mode: str,
        return_margin: int,
        edge_profiles: Optional[Dict[str, ServerTarget]] = None,
    ) -> None:
        self.server_host = server_host
        self.server_port = server_port
        self.token = token
        self._edge_profiles: Dict[str, ServerTarget] = {}
        if edge_profiles:
            for edge_name, target in edge_profiles.items():
                normalized = edge_name.lower()
                host, port, auth = target
                self._edge_profiles[normalized] = (host, int(port), auth)
        self.edge = edge
        self.edge_margin = edge_margin
        self.edge_delay = edge_delay
        self.toggle_hotkey = toggle_hotkey
        self.back_hotkey = back_hotkey
        self.heartbeat = heartbeat
        self.auto_return = True
        self.return_margin = max(1, int(return_margin))

        self._connection: Optional[socket.socket] = None
        self._reader = None
        self._writer = None
        self._writer_lock = threading.Lock()
        self._stop = threading.Event()
        self._remote_active = threading.Event()
        self._connected = threading.Event()
        self._connection_lock = threading.Lock()
        self._mouse_listener = None
        self._keyboard_listener = None
        self._last_mouse_pos: Optional[Tuple[int, int]] = None
        self._connection_thread: Optional[threading.Thread] = None
        self._active_edge: Optional[str] = None
        self._last_auto_edge: Optional[str] = None

        self._mouse, self._keyboard = import_pynput()
        self._cursor_manager = LocalCursorManager(self._mouse, local_cursor_mode)
        self._edge_crossing_data: Optional[Dict[str, Any]] = None
        self._cursor_adapter = CursorAdapter(self._mouse)
        self._pending_server: Optional[ServerTarget] = None
        self._pending_lock = threading.Lock()
        self._reconnect = threading.Event()
        self._wakeup = threading.Event()

        self._mac_event_supported = False
        self._mac_event_thread: Optional[threading.Thread] = None
        self._mac_event_stop = threading.Event()
        self._mac_event_ready = threading.Event()
        self._mac_event_runloop = None
        self._mac_event_tap = None
        self._mac_last_flags = 0
        self._mac_keycode_map: Dict[int, Any] = {}
        self._mac_modifier_masks: Dict[int, int] = {}
        self._using_mac_tap = False
        self._toggle_hotkey = None
        self._back_hotkey = None

        if sys.platform == "darwin":
            try:
                import Quartz.CoreGraphics as CG  # type: ignore
                import CoreFoundation  # type: ignore

                self._CG = CG
                self._CF = CoreFoundation
                self._mac_event_supported = True
                self._mac_keycode_map = self._build_mac_key_map()
                self._mac_modifier_masks = self._build_mac_modifier_masks()
            except Exception as exc:  # pragma: no cover - mac-only
                LOG.debug("Quartz event tap unavailable: %s", exc)
                self._mac_event_supported = False


    def run(self) -> None:
        self._start_connection_manager()
        if not self._connected.wait(timeout=10.0):
            LOG.warning("Initial connection to server pending; will keep retrying in background")
        threads = [
            threading.Thread(target=self._heartbeat_loop, daemon=True),
            threading.Thread(target=self._edge_loop, daemon=True),
        ]
        for t in threads:
            t.start()

        toggle = self._keyboard.HotKey(
            self._parse_hotkey(self.toggle_hotkey, DEFAULT_TOGGLE_HOTKEY),
            lambda: self.activate_remote("hotkey"),
        )
        back = self._keyboard.HotKey(
            self._parse_hotkey(self.back_hotkey, DEFAULT_BACK_HOTKEY),
            self.deactivate_remote,
        )

        self._toggle_hotkey = toggle
        self._back_hotkey = back

        if self._start_mac_event_tap():
            try:
                LOG.info(
                    "Client ready. Toggle remote control with %s, return with %s",
                    self.toggle_hotkey,
                    self.back_hotkey,
                )
                while not self._stop.wait(timeout=0.5):
                    pass
            except KeyboardInterrupt:
                self._stop.set()
        else:
            def on_press(key):
                toggle.press(key)
                back.press(key)

            def on_release(key):
                toggle.release(key)
                back.release(key)

            hotkey_listener = self._keyboard.Listener(on_press=on_press, on_release=on_release)

            with hotkey_listener:
                LOG.info(
                    "Client ready. Toggle remote control with %s, return with %s",
                    self.toggle_hotkey,
                    self.back_hotkey,
                )
                try:
                    hotkey_listener.join()
                except KeyboardInterrupt:
                    self._stop.set()

        self._stop.set()
        self.deactivate_remote()
        LOG.info("Client exiting")
        self._stop_mac_event_tap()
        self._reset_connection_state()
        if self._connection_thread and self._connection_thread.is_alive():
            self._connection_thread.join(timeout=2.0)
        for t in threads:
            if t.is_alive():
                t.join(timeout=1.0)

    def _start_connection_manager(self) -> None:
        if self._connection_thread and self._connection_thread.is_alive():
            return
        self._connection_thread = threading.Thread(target=self._connection_loop, daemon=True)
        self._connection_thread.start()

    def _current_server_target(self) -> ServerTarget:
        return (self.server_host, self.server_port, self.token)

    def _resolve_profile_for_edge(self, edge: Optional[str]) -> Optional[ServerTarget]:
        if not self._edge_profiles:
            return None
        if edge:
            profile = self._edge_profiles.get(edge)
            if profile:
                return profile
        return self._edge_profiles.get("default")

    def _ensure_connection_for_edge(self, edge: Optional[str]) -> bool:
        profile = self._resolve_profile_for_edge(edge)
        if not profile:
            return True
        if self._connected.is_set() and self._current_server_target() == profile:
            return True
        self._switch_server(profile)
        self._start_connection_manager()
        if not self._connected.wait(timeout=10.0):
            edge_label = edge or "default"
            LOG.error(
                "Unable to connect to configured server for edge '%s' (%s:%d)",
                edge_label,
                profile[0],
                profile[1],
            )
            return False
        return True

    def _switch_server(self, profile: ServerTarget) -> None:
        current = self._current_server_target()
        if current == profile and not self._connected.is_set():
            # Already targeting the desired server; just wake the connector.
            self._wakeup.set()
            return
        if current == profile and self._connected.is_set():
            return
        LOG.info("Switching to server %s:%d", profile[0], profile[1])
        with self._pending_lock:
            self._pending_server = profile
        self._reconnect.set()
        self._wakeup.set()
        self._connected.clear()
        self.deactivate_remote(reason="server_switch", notify_server=False)
        self._reset_connection_state()

    def _wait_for_wakeup(self, timeout: float) -> str:
        deadline = time.time() + timeout
        while True:
            if self._stop.is_set():
                return "stop"
            if self._wakeup.is_set():
                self._wakeup.clear()
                return "wakeup"
            remaining = deadline - time.time()
            if remaining <= 0:
                return "timeout"
            time.sleep(min(0.1, remaining))

    # --- macOS event tap helpers -------------------------------------------------

    def _build_mac_key_map(self) -> Dict[int, Any]:  # pragma: no cover - mac-only
        keyboard = self._keyboard
        Key = keyboard.Key
        KeyCode = keyboard.KeyCode

        def key(name: str, fallback: Optional[str] = None):
            return getattr(Key, name, getattr(Key, fallback, None))

        mapping: Dict[int, Any] = {}

        char_map = {
            0: "a",
            1: "s",
            2: "d",
            3: "f",
            4: "h",
            5: "g",
            6: "z",
            7: "x",
            8: "c",
            9: "v",
            11: "b",
            12: "q",
            13: "w",
            14: "e",
            15: "r",
            16: "y",
            17: "t",
            18: "1",
            19: "2",
            20: "3",
            21: "4",
            22: "6",
            23: "5",
            24: "=",
            25: "9",
            26: "7",
            27: "-",
            28: "8",
            29: "0",
            30: "]",
            31: "o",
            32: "u",
            33: "[",
            34: "i",
            35: "p",
            37: "l",
            38: "j",
            39: "'",
            40: "k",
            41: ";",
            42: "\\",
            43: ",",
            44: "/",
            45: "n",
            46: "m",
            47: ".",
            50: "`",
        }

        for code, value in char_map.items():
            try:
                mapping[code] = KeyCode.from_char(value)
            except Exception:
                pass

        special_map = {
            36: key("enter"),
            48: key("tab"),
            49: key("space"),
            51: key("backspace"),
            52: key("enter"),
            53: key("esc"),
            54: key("cmd_r", "cmd"),
            55: key("cmd"),
            56: key("shift"),
            57: key("caps_lock"),
            58: key("alt"),
            59: key("ctrl"),
            60: key("shift_r", "shift"),
            61: key("alt_r", "alt"),
            62: key("ctrl_r", "ctrl"),
            63: key("fn", None),
            64: key("f17", None),
            65: KeyCode.from_char("."),
            67: key("multiply", None),
            69: key("add", None),
            71: key("clear", None),
            75: key("divide", None),
            76: key("enter", None),
            78: key("subtract", None),
            81: key("equals", None),
            96: key("f5", None),
            97: key("f6", None),
            98: key("f7", None),
            99: key("f3", None),
            100: key("f8", None),
            101: key("f9", None),
            103: key("f11", None),
            109: key("f10", None),
            111: key("f12", None),
            114: key("help", None),
            115: key("home", None),
            116: key("page_up", None),
            117: key("delete", None),
            118: key("f4", None),
            119: key("end", None),
            120: key("f2", None),
            121: key("page_down", None),
            122: key("f1", None),
            123: key("left"),
            124: key("right"),
            125: key("down"),
            126: key("up"),
        }

        for code, value in special_map.items():
            if value is not None:
                mapping[code] = value

        keypad_map = {
            82: "0",
            83: "1",
            84: "2",
            85: "3",
            86: "4",
            87: "5",
            88: "6",
            89: "7",
            91: "8",
            92: "9",
        }
        for code, value in keypad_map.items():
            try:
                mapping[code] = KeyCode.from_char(value)
            except Exception:
                pass

        return mapping

    def _build_mac_modifier_masks(self) -> Dict[int, int]:  # pragma: no cover - mac-only
        CG = getattr(self, "_CG", None)
        if not CG:
            return {}
        return {
            54: CG.kCGEventFlagMaskCommand,
            55: CG.kCGEventFlagMaskCommand,
            56: CG.kCGEventFlagMaskShift,
            57: CG.kCGEventFlagMaskAlphaShift,
            58: CG.kCGEventFlagMaskAlternate,
            59: CG.kCGEventFlagMaskControl,
            60: CG.kCGEventFlagMaskShift,
            61: CG.kCGEventFlagMaskAlternate,
            62: CG.kCGEventFlagMaskControl,
        }

    def _start_mac_event_tap(self) -> bool:  # pragma: no cover - mac-only
        if not self._mac_event_supported:
            return False
        if self._mac_event_thread and self._mac_event_thread.is_alive():
            self._using_mac_tap = True
            return True
        self._mac_event_stop.clear()
        self._mac_event_ready.clear()
        thread = threading.Thread(target=self._mac_event_loop, daemon=True)
        self._mac_event_thread = thread
        thread.start()
        if not self._mac_event_ready.wait(timeout=2.0):
            LOG.warning("Timed out initialising macOS event tap; falling back to pynput")
            self._mac_event_supported = False
            self._mac_event_thread = None
            return False
        if self._mac_event_tap is None:
            self._mac_event_supported = False
            self._mac_event_thread = None
            return False
        self._using_mac_tap = True
        return True

    def _stop_mac_event_tap(self) -> None:  # pragma: no cover - mac-only
        if not self._mac_event_thread:
            return
        self._mac_event_stop.set()
        try:
            if self._mac_event_runloop is not None:
                cf = getattr(self, "_CF", None)
                if cf is not None:
                    cf.CFRunLoopStop(self._mac_event_runloop)
        except Exception:
            pass
        self._mac_event_thread.join(timeout=1.5)
        self._mac_event_thread = None
        self._mac_event_runloop = None
        self._mac_event_tap = None
        self._using_mac_tap = False

    def _mac_event_loop(self) -> None:  # pragma: no cover - mac-only
        CG = self._CG
        CF = self._CF

        mask = 0
        mouse_events = [
            CG.kCGEventMouseMoved,
            CG.kCGEventLeftMouseDown,
            CG.kCGEventLeftMouseUp,
            CG.kCGEventRightMouseDown,
            CG.kCGEventRightMouseUp,
            CG.kCGEventOtherMouseDown,
            CG.kCGEventOtherMouseUp,
            CG.kCGEventScrollWheel,
            CG.kCGEventLeftMouseDragged,
            CG.kCGEventRightMouseDragged,
            CG.kCGEventOtherMouseDragged,
        ]
        key_events = [
            CG.kCGEventKeyDown,
            CG.kCGEventKeyUp,
            CG.kCGEventFlagsChanged,
        ]

        for event_id in mouse_events + key_events:
            mask |= 1 << event_id

        def callback(proxy, type_, event, refcon):  # noqa: ANN001
            return self._mac_handle_cg_event(type_, event)

        tap = CG.CGEventTapCreate(
            CG.kCGSessionEventTap,
            CG.kCGHeadInsertEventTap,
            CG.kCGEventTapOptionDefault,
            mask,
            callback,
            None,
        )

        if not tap:
            LOG.warning("Unable to create macOS event tap; ensure Accessibility permissions are granted")
            self._mac_event_tap = None
            self._mac_event_ready.set()
            return

        run_loop_source = CG.CFMachPortCreateRunLoopSource(None, tap, 0)
        loop = CF.CFRunLoopGetCurrent()
        self._mac_event_runloop = loop
        CF.CFRunLoopAddSource(loop, run_loop_source, CF.kCFRunLoopCommonModes)
        CG.CGEventTapEnable(tap, True)
        self._mac_event_tap = tap
        self._mac_last_flags = int(CG.CGEventSourceFlagsState(CG.kCGEventSourceStateCombinedSessionState))
        self._mac_event_ready.set()

        while not self._mac_event_stop.is_set():
            CF.CFRunLoopRunInMode(CF.kCFRunLoopDefaultMode, 0.05, True)

        CG.CGEventTapEnable(tap, False)
        CF.CFRunLoopRemoveSource(loop, run_loop_source, CF.kCFRunLoopCommonModes)
        CG.CFMachPortInvalidate(tap)

    def _mac_handle_cg_event(self, type_, event):  # pragma: no cover - mac-only
        CG = self._CG
        if type_ in {CG.kCGEventTapDisabledByTimeout, CG.kCGEventTapDisabledByUserInput}:
            try:
                CG.CGEventTapEnable(self._mac_event_tap, True)
            except Exception:
                pass
            return event

        suppress = self._remote_active.is_set()

        try:
            if type_ in (
                CG.kCGEventMouseMoved,
                CG.kCGEventLeftMouseDragged,
                CG.kCGEventRightMouseDragged,
                CG.kCGEventOtherMouseDragged,
            ):
                loc = CG.CGEventGetLocation(event)
                self._on_move(int(loc.x), int(loc.y))
                return None if suppress else event

            if type_ in (
                CG.kCGEventLeftMouseDown,
                CG.kCGEventLeftMouseUp,
                CG.kCGEventRightMouseDown,
                CG.kCGEventRightMouseUp,
                CG.kCGEventOtherMouseDown,
                CG.kCGEventOtherMouseUp,
            ):
                button_name = self._mac_translate_button(event)
                loc = CG.CGEventGetLocation(event)
                pressed = type_ in (
                    CG.kCGEventLeftMouseDown,
                    CG.kCGEventRightMouseDown,
                    CG.kCGEventOtherMouseDown,
                )
                button = _MacButton(button_name)
                self._on_click(int(loc.x), int(loc.y), button, pressed)
                return None if suppress else event

            if type_ == CG.kCGEventScrollWheel:
                dy = CG.CGEventGetIntegerValueField(event, CG.kCGScrollWheelEventDeltaAxis1)
                dx = CG.CGEventGetIntegerValueField(event, CG.kCGScrollWheelEventDeltaAxis2)
                loc = CG.CGEventGetLocation(event)
                self._on_scroll(int(loc.x), int(loc.y), int(dx), int(dy))
                return None if suppress else event

            if type_ in (CG.kCGEventKeyDown, CG.kCGEventKeyUp, CG.kCGEventFlagsChanged):
                keycode = int(CG.CGEventGetIntegerValueField(event, CG.kCGKeyboardEventKeycode))
                flags = int(CG.CGEventGetFlags(event))
                if type_ == CG.kCGEventFlagsChanged:
                    mask = self._mac_modifier_masks.get(keycode)
                    if mask is None:
                        self._mac_last_flags = flags
                        return event
                    pressed = bool(flags & mask)
                else:
                    pressed = type_ == CG.kCGEventKeyDown
                key_obj = self._mac_keycode_map.get(keycode)
                if key_obj is None:
                    self._mac_last_flags = flags
                    return event
                try:
                    if self._toggle_hotkey and self._back_hotkey:
                        if pressed:
                            self._toggle_hotkey.press(key_obj)
                            self._back_hotkey.press(key_obj)
                        else:
                            self._toggle_hotkey.release(key_obj)
                            self._back_hotkey.release(key_obj)
                except Exception:
                    pass
                if pressed:
                    self._on_press(key_obj)
                else:
                    self._on_release(key_obj)
                self._mac_last_flags = flags
                return None if suppress else event

        except Exception as exc:
            LOG.debug("macOS event tap error: %s", exc)
        return event

    def _mac_translate_button(self, event) -> str:  # pragma: no cover - mac-only
        CG = self._CG
        button = int(CG.CGEventGetIntegerValueField(event, CG.kCGMouseEventButtonNumber))
        if button == CG.kCGMouseButtonLeft:
            return "left"
        if button == CG.kCGMouseButtonRight:
            return "right"
        if button == 2:
            return "middle"
        return "left"

    def _connection_loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            if self._reconnect.is_set():
                with self._pending_lock:
                    pending = self._pending_server
                    self._pending_server = None
                self._reconnect.clear()
                if pending:
                    current = self._current_server_target()
                    if current != pending:
                        LOG.debug(
                            "Pending server target set to %s:%d", pending[0], pending[1]
                        )
                    self.server_host, self.server_port, self.token = pending
            try:
                self._establish_connection()
                self._connected.set()
                backoff = 1.0
                self._reader_worker()
            except (ConnectionError, ProtocolError, OSError) as exc:
                if self._stop.is_set():
                    break
                LOG.warning("Connection to server interrupted: %s", exc)
            finally:
                self._connected.clear()
                self.deactivate_remote(reason="connection_lost", notify_server=False)
                self._reset_connection_state()
            outcome = self._wait_for_wakeup(backoff)
            if outcome == "stop":
                break
            if outcome == "wakeup":
                backoff = 1.0
                continue
            backoff = min(backoff * 2, 30.0)

    def _establish_connection(self) -> None:
        LOG.info("Connecting to %s:%d", self.server_host, self.server_port)
        sock = socket.create_connection((self.server_host, self.server_port), timeout=10)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        reader = sock.makefile("rb")
        writer = sock.makefile("wb")
        assigned = False
        try:
            hello = build_client_hello(self.token)
            writer.write(json_dumps(hello))
            writer.flush()
            response = reader.readline()
            if not response:
                raise ConnectionError("Server closed connection during handshake")
            reply = json.loads(response.decode("utf-8"))
            validate_server_welcome(reply)
            with self._connection_lock:
                self._connection = sock
                self._reader = reader
                self._writer = writer
            assigned = True
            LOG.info("Connected to server")
        except (ConnectionError, ProtocolError):
            raise
        except Exception as exc:
            raise ConnectionError(f"Failed during handshake: {exc}") from exc
        finally:
            if not assigned:
                with contextlib.suppress(Exception):
                    writer.close()
                with contextlib.suppress(Exception):
                    reader.close()
                with contextlib.suppress(Exception):
                    sock.close()

    def _reader_worker(self) -> None:
        while not self._stop.is_set():
            with self._connection_lock:
                reader = self._reader
            if reader is None:
                return
            try:
                line = reader.readline()
            except OSError as exc:
                if self._stop.is_set():
                    return
                raise ConnectionError(f"Error reading from server: {exc}") from exc
            if not line:
                raise ConnectionError("Server closed the connection")
            try:
                message = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                LOG.debug("Discarding malformed message from server")
                continue
            self._handle_server_message(message)

    def _send(self, payload: Dict) -> None:
        if not self._connected.is_set():
            raise ConnectionError("Not connected to server")
        with self._connection_lock:
            connection = self._connection
            writer = self._writer
        if not connection or not writer:
            raise ConnectionError("Not connected to server")
        data = json_dumps(payload)
        with self._writer_lock:
            try:
                writer.write(data)
                writer.flush()
            except OSError as exc:
                raise ConnectionError("Failed to send payload") from exc

    def _reset_connection_state(self) -> None:
        with self._connection_lock:
            sock = self._connection
            reader = self._reader
            writer = self._writer
            self._connection = None
            self._reader = None
            self._writer = None
        if writer:
            with contextlib.suppress(Exception):
                writer.close()
        if reader:
            with contextlib.suppress(Exception):
                reader.close()
        if sock:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(Exception):
                sock.close()

    def _handle_server_message(self, message: Dict[str, Any]) -> None:
        mtype = message.get("type")
        if mtype == "edge_exit":
            if not self.auto_return or not self._remote_active.is_set():
                return
            ratio_value = message.get("ratio", 0.5)
            release_edge = message.get("edge")
            if isinstance(release_edge, str) and release_edge in OPPOSITE_EDGE:
                self._last_auto_edge = OPPOSITE_EDGE[release_edge]
            LOG.info(
                "Remote requested return via %s edge (ratio=%.3f)",
                message.get("edge"),
                float(ratio_value) if isinstance(ratio_value, (int, float)) else 0.5,
            )
            edge_data = {"edge": message.get("edge"), "ratio": ratio_value}
            self.deactivate_remote(reason="edge_exit", edge_data=edge_data)
        elif mtype == "error":
            reason = message.get("reason")
            detail = message.get("message")
            if detail:
                LOG.error("Server reported error: %s (%s)", reason, detail)
            else:
                LOG.error("Server reported error: %s", reason)
        else:
            LOG.debug("Ignoring message from server: %s", message)

    def activate_remote(self, reason: str, edge_override: Optional[str] = None) -> None:
        if self._remote_active.is_set():
            return
        edge_for_session = self._resolve_active_edge(edge_override)
        if not self._ensure_connection_for_edge(edge_for_session):
            LOG.warning(
                "Remote session aborted: server unavailable for edge '%s'",
                edge_for_session or "default",
            )
            return
        if not self._connected.is_set():
            LOG.warning("Cannot start remote session: not connected to server")
            return
        LOG.info("Remote session starting (%s)", reason)
        self._remote_active.set()
        release_edge = None
        if edge_for_session and edge_for_session in OPPOSITE_EDGE:
            release_edge = OPPOSITE_EDGE[edge_for_session]
        elif self._last_auto_edge and self._last_auto_edge in OPPOSITE_EDGE:
            release_edge = OPPOSITE_EDGE[self._last_auto_edge]
        elif self.edge in OPPOSITE_EDGE:
            release_edge = OPPOSITE_EDGE[self.edge]
        try:
            payload: Dict[str, Any] = {"type": "session", "state": "start", "reason": reason}
            self._active_edge = edge_for_session
            if edge_for_session:
                payload["edge"] = edge_for_session
                self._last_auto_edge = edge_for_session
            if release_edge:
                payload["release_edge"] = release_edge
            payload["auto_return"] = self.auto_return
            payload["return_margin"] = self.return_margin
            payload["edge_margin"] = self.edge_margin
            self._send(payload)
        except ConnectionError as exc:
            LOG.error("Unable to start remote session: %s", exc)
            self._remote_active.clear()
            return
        self._start_captors()
        self._cursor_manager.on_remote_start(self._active_edge, self.edge_margin)
        try:
            align_payload = None
            if reason == "edge" and self._edge_crossing_data:
                align_payload = {"type": "move_to_edge", **self._edge_crossing_data}
            else:
                entry_edge = edge_for_session or self._last_auto_edge
                if entry_edge:
                    align_payload = self._compute_alignment_payload(entry_edge)
            if align_payload:
                self._send(align_payload)
        except ConnectionError as exc:
            LOG.warning("Failed to align cursor on remote edge: %s", exc)
        finally:
            self._edge_crossing_data = None

    def _resolve_active_edge(self, override: Optional[str]) -> Optional[str]:
        candidate = override
        if candidate in {"auto", "none"}:
            candidate = None if candidate == "none" else self._last_auto_edge
        if candidate:
            return candidate
        base = self.edge
        if base in {"auto", "none"}:
            base = None if base == "none" else self._last_auto_edge
        if base:
            return base
        return self._last_auto_edge

    def _compute_alignment_payload(self, edge_name: str) -> Optional[Dict[str, Any]]:
        try:
            x, y = self._cursor_adapter.position()
            width, height = self._cursor_adapter.size()
        except Exception:
            return None
        ratio = self._calculate_ratio(edge_name, x, y, width, height)
        return {"type": "move_to_edge", "edge": edge_name, "ratio": ratio}

    def deactivate_remote(
        self,
        reason: str = "manual",
        edge_data: Optional[Dict[str, Any]] = None,
        notify_server: bool = True,
    ) -> None:
        was_active = self._remote_active.is_set()
        if was_active:
            LOG.info("Remote session stopping (%s)", reason)
            self._remote_active.clear()
        else:
            notify_server = False
        try:
            if was_active and notify_server and self._connected.is_set():
                payload: Dict[str, Any] = {"type": "session", "state": "stop", "reason": reason}
                self._send(payload)
        except ConnectionError as exc:
            LOG.warning("Failed to notify server about session stop: %s", exc)
        finally:
            if was_active:
                self._stop_captors()
                self._cursor_manager.on_remote_stop()
                if edge_data:
                    self._restore_local_cursor(edge_data)
                self._edge_crossing_data = None
                self._active_edge = None

    def _restore_local_cursor(self, edge_data: Dict[str, Any]) -> None:
        edge_for_restore = self._active_edge
        if not edge_for_restore:
            release_edge = edge_data.get("edge")
            if isinstance(release_edge, str):
                edge_for_restore = OPPOSITE_EDGE.get(release_edge)
        if not edge_for_restore:
            return
        try:
            ratio = float(edge_data.get("ratio", 0.5))
        except (TypeError, ValueError):
            ratio = 0.5
        ratio = max(0.0, min(1.0, ratio))
        cursor = self._cursor_adapter
        width = height = None
        try:
            width, height = cursor.size()
        except Exception:
            pass
        if not width or not height:
            try:
                pyautogui = import_pyautogui()
                size = pyautogui.size()
                width, height = int(size[0]), int(size[1])
                cursor = None  # force fallback
            except Exception:
                return
        if not width or not height:
            return
        margin = max(1, self.edge_margin)
        x = width // 2
        y = height // 2
        if edge_for_restore == "right":
            x = max(width - margin, 0)
            y = int(ratio * max(height - 1, 1))
        elif edge_for_restore == "left":
            x = min(margin, max(width - 1, 0))
            y = int(ratio * max(height - 1, 1))
        elif edge_for_restore == "top":
            x = int(ratio * max(width - 1, 1))
            y = min(margin, max(height - 1, 0))
        elif edge_for_restore == "bottom":
            x = int(ratio * max(width - 1, 1))
            y = max(height - margin, 0)
        try:
            if cursor:
                cursor.move_to(int(x), int(y))
            else:
                pyautogui.FAILSAFE = False  # type: ignore[name-defined]
                pyautogui.moveTo(int(x), int(y))  # type: ignore[name-defined]
        except Exception:
            pass

    def _start_captors(self) -> None:
        if self._using_mac_tap:
            return
        if self._mouse_listener or self._keyboard_listener:
            return

        self._last_mouse_pos = None

        self._mouse_listener = self._init_listener(
            lambda suppress: self._mouse.Listener(
                on_move=self._on_move,
                on_click=self._on_click,
                on_scroll=self._on_scroll,
                suppress=suppress,
            ),
            "mouse",
        )

        self._keyboard_listener = self._init_listener(
            lambda suppress: self._keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
                suppress=suppress,
            ),
            "keyboard",
        )

        if not self._mouse_listener or not self._keyboard_listener:
            LOG.error("Failed to initialise local input capture; stopping remote session")
            self.deactivate_remote(reason="capture_unavailable")

    def _stop_captors(self) -> None:
        if self._using_mac_tap:
            return
        for listener in (self._mouse_listener, self._keyboard_listener):
            if listener:
                listener.stop()
        if self._mouse_listener:
            self._mouse_listener.join()
        if self._keyboard_listener:
            self._keyboard_listener.join()
        self._mouse_listener = None
        self._keyboard_listener = None
        self._last_mouse_pos = None

    def _init_listener(self, factory, kind: str):
        for suppress in (True, False):
            try:
                listener = factory(suppress)
            except Exception as exc:
                if suppress:
                    self._report_listener_issue(kind, exc)
                    continue
                LOG.error("Unable to create %s listener: %s", kind, exc)
                return None
            try:
                listener.start()
                if not suppress:
                    LOG.warning(
                        "%s listener running without suppression; local inputs may leak", kind.capitalize()
                    )
                return listener
            except Exception as exc:
                with contextlib.suppress(Exception):
                    listener.stop()
                if suppress:
                    self._report_listener_issue(kind, exc)
                    continue
                LOG.error("Unable to start %s listener: %s", kind, exc)
                return None
        return None

    def _report_listener_issue(self, kind: str, exc: Exception) -> None:
        LOG.warning("Unable to start %s listener with event suppression: %s", kind, exc)
        if sys.platform == "darwin":
            LOG.warning(
                "Grant Accessibility permissions to Flowlite (System Settings > Privacy & Security > Accessibility)."
            )

    def _on_move(self, x: int, y: int):
        if not self._remote_active.is_set():
            return
        if self._last_mouse_pos is None:
            self._last_mouse_pos = (x, y)
            return
        dx = x - self._last_mouse_pos[0]
        dy = y - self._last_mouse_pos[1]
        self._last_mouse_pos = (x, y)
        if dx or dy:
            self._send({"type": "move", "dx": dx, "dy": dy})

    def _on_click(self, x: int, y: int, button, pressed: bool):
        if not self._remote_active.is_set():
            return
        self._send({"type": "click", "button": button.name, "pressed": pressed})

    def _on_scroll(self, x: int, y: int, dx: int, dy: int):
        if not self._remote_active.is_set():
            return
        self._send({"type": "scroll", "dx": dx, "dy": dy})

    def _on_press(self, key):
        if not self._remote_active.is_set():
            return
        formatted = format_key(key)
        if formatted:
            self._send({"type": "key", "key": formatted, "pressed": True})

    def _on_release(self, key):
        if not self._remote_active.is_set():
            return
        formatted = format_key(key)
        if formatted:
            self._send({"type": "key", "key": formatted, "pressed": False})

    def _heartbeat_loop(self) -> None:
        if self.heartbeat <= 0:
            return
        while not self._stop.wait(self.heartbeat):
            if not self._connected.is_set():
                continue
            try:
                self._send({"type": "heartbeat", "ts": time.time()})
            except ConnectionError as exc:
                LOG.error("Heartbeat failed: %s", exc)
                self._stop.set()
                break

    def _edge_loop(self) -> None:
        if not self.edge or self.edge == "none":
            return
        watched_edges = self._edges_to_watch()
        if not watched_edges:
            return
        cursor = self._cursor_adapter
        pyautogui_fallback = None
        pending_start: Dict[str, float] = {}
        poll = 0.05
        while not self._stop.wait(poll):
            if self._remote_active.is_set():
                pending_start.clear()
                continue
            if not self._connected.is_set():
                pending_start.clear()
                continue
            try:
                x, y = cursor.position()
                width, height = cursor.size()
            except Exception:
                if pyautogui_fallback is None:
                    try:
                        pyautogui_fallback = import_pyautogui()
                    except Exception:
                        continue
                try:
                    pos = pyautogui_fallback.position()
                    x, y = int(pos[0]), int(pos[1])
                    size = pyautogui_fallback.size()
                    width, height = int(size[0]), int(size[1])
                except Exception:
                    continue
            if width <= 1 or height <= 1:
                continue
            triggered_edge = None
            now = time.time()
            for edge_name in watched_edges:
                if self._is_on_edge(edge_name, x, y, width, height):
                    start = pending_start.get(edge_name)
                    if start is None:
                        pending_start[edge_name] = now
                        continue
                    if now - start < self.edge_delay:
                        continue
                    triggered_edge = edge_name
                    break
                else:
                    pending_start.pop(edge_name, None)
            if not triggered_edge:
                continue
            ratio = self._calculate_ratio(triggered_edge, x, y, width, height)
            self._edge_crossing_data = {"edge": triggered_edge, "ratio": ratio}
            if self.edge == "auto":
                self._last_auto_edge = triggered_edge
            self.activate_remote("edge", edge_override=triggered_edge)
            pending_start.clear()

    def _edges_to_watch(self) -> Optional[Tuple[str, ...]]:
        if not self.edge or self.edge == "none":
            return None
        if self.edge == "auto":
            return ("left", "right", "top", "bottom")
        return (self.edge,)

    def _is_on_edge(self, edge: str, x: int, y: int, width: int, height: int) -> bool:
        m = self.edge_margin
        if edge == "right":
            return x >= width - m
        if edge == "left":
            return x <= m
        if edge == "top":
            return y <= m
        if edge == "bottom":
            return y >= height - m
        return False

    def _calculate_ratio(self, edge: str, x: int, y: int, width: int, height: int) -> float:
        if edge in {"right", "left"} and height:
            return max(0.0, min(1.0, y / max(height - 1, 1)))
        if edge in {"top", "bottom"} and width:
            return max(0.0, min(1.0, x / max(width - 1, 1)))
        return 0.5

    def _normalize_hotkey(self, combo: str) -> str:
        def repl(match: re.Match[str]) -> str:
            token = match.group(1).strip().lower()
            mapping = {
                "option": "alt",
                "opt": "alt",
                "command": "cmd",
                "control": "ctrl",
                "ctl": "ctrl",
                "windows": "cmd",
                "win": "cmd",
            }
            normalized = mapping.get(token, token)
            return f"<{normalized}>"

        return re.sub(r"<([^>]+)>", repl, combo)

    def _parse_hotkey(self, combo: str, fallback: str):
        normalized = self._normalize_hotkey(combo)
        try:
            return self._keyboard.HotKey.parse(normalized)
        except Exception:
            fallback_normalized = self._normalize_hotkey(fallback)
            LOG.warning("Unable to parse hotkey '%s'; falling back to '%s'", combo, fallback)
            return self._keyboard.HotKey.parse(fallback_normalized)
