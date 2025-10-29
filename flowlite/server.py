from __future__ import annotations

import contextlib
import json
import socket
import threading
import time
import sys
from typing import Any, Callable, Dict, Optional, Tuple

from .cursor import CursorAdapter
from .keys import OPPOSITE_EDGE, SPECIAL_KEY_MAP
from .protocol import ProtocolError, build_server_welcome, validate_client_hello
from .utils import LOG, import_pynput, import_pyautogui, json_dumps


class _MacEventSender:
    def __init__(self, cursor: CursorAdapter) -> None:  # pragma: no cover - mac-only
        import Quartz.CoreGraphics as CG  # type: ignore

        self._cursor = cursor
        self._CG = CG
        self._source = CG.CGEventSourceCreate(CG.kCGEventSourceStateCombinedSessionState)
        self._char_keycodes = self._build_char_keycodes()
        self._special_keycodes = self._build_special_keycodes()

    def move_rel(self, dx: int, dy: int) -> bool:
        if dx == 0 and dy == 0:
            return True
        try:
            x, y = self._cursor.position()
        except Exception:
            return False
        return self.move_to(x + dx, y + dy)

    def move_to(self, x: int, y: int) -> bool:
        CG = self._CG
        event = CG.CGEventCreateMouseEvent(
            self._source,
            CG.kCGEventMouseMoved,
            (float(x), float(y)),
            CG.kCGMouseButtonLeft,
        )
        if not event:
            return False
        CG.CGEventPost(CG.kCGHIDEventTap, event)
        return True

    def click(self, button_name: str, pressed: bool) -> bool:
        CG = self._CG
        button_map = {
            "left": CG.kCGMouseButtonLeft,
            "right": CG.kCGMouseButtonRight,
            "middle": 2,
        }
        button = button_map.get(button_name, CG.kCGMouseButtonLeft)
        try:
            x, y = self._cursor.position()
        except Exception:
            return False
        event_type_map = {
            (CG.kCGMouseButtonLeft, True): CG.kCGEventLeftMouseDown,
            (CG.kCGMouseButtonLeft, False): CG.kCGEventLeftMouseUp,
            (CG.kCGMouseButtonRight, True): CG.kCGEventRightMouseDown,
            (CG.kCGMouseButtonRight, False): CG.kCGEventRightMouseUp,
        }
        event_type = event_type_map.get((button, pressed))
        if event_type is None:
            event_type = CG.kCGEventOtherMouseDown if pressed else CG.kCGEventOtherMouseUp
        event = CG.CGEventCreateMouseEvent(
            self._source,
            event_type,
            (float(x), float(y)),
            button,
        )
        if not event:
            return False
        CG.CGEventPost(CG.kCGHIDEventTap, event)
        return True

    def scroll(self, dx: int, dy: int) -> bool:
        CG = self._CG
        event = CG.CGEventCreateScrollWheelEvent(
            self._source,
            CG.kCGScrollEventUnitLine,
            2,
            int(dy),
            int(dx),
        )
        if not event:
            return False
        CG.CGEventPost(CG.kCGHIDEventTap, event)
        return True

    def key_event(self, token: str, pressed: bool) -> bool:
        CG = self._CG
        keycode = None
        if token.startswith("<") and token.endswith(">"):
            name = token[1:-1].lower()
            keycode = self._special_keycodes.get(name)
        else:
            lookup = token.lower()
            keycode = self._char_keycodes.get(lookup)
        if keycode is None:
            return False
        event = CG.CGEventCreateKeyboardEvent(self._source, keycode, pressed)
        if not event:
            return False
        if len(token) == 1:
            CG.CGEventKeyboardSetUnicodeString(event, 1, token)
        CG.CGEventPost(CG.kCGHIDEventTap, event)
        return True

    def _build_char_keycodes(self) -> Dict[str, int]:  # pragma: no cover - mac-only
        mapping = {
            "a": 0,
            "s": 1,
            "d": 2,
            "f": 3,
            "h": 4,
            "g": 5,
            "z": 6,
            "x": 7,
            "c": 8,
            "v": 9,
            "b": 11,
            "q": 12,
            "w": 13,
            "e": 14,
            "r": 15,
            "y": 16,
            "t": 17,
            "1": 18,
            "2": 19,
            "3": 20,
            "4": 21,
            "6": 22,
            "5": 23,
            "=": 24,
            "9": 25,
            "7": 26,
            "-": 27,
            "8": 28,
            "0": 29,
            "]": 30,
            "o": 31,
            "u": 32,
            "[": 33,
            "i": 34,
            "p": 35,
            "l": 37,
            "j": 38,
            "'": 39,
            "k": 40,
            ";": 41,
            "\\": 42,
            ",": 43,
            "/": 44,
            "n": 45,
            "m": 46,
            ".": 47,
            "`": 50,
        }
        return mapping

    def _build_special_keycodes(self) -> Dict[str, int]:  # pragma: no cover - mac-only
        return {
            "return": 36,
            "enter": 36,
            "tab": 48,
            "space": 49,
            "backspace": 51,
            "delete": 117,
            "esc": 53,
            "escape": 53,
            "cmd": 55,
            "cmd_l": 55,
            "cmd_r": 54,
            "command": 55,
            "shift": 56,
            "shift_r": 60,
            "caps_lock": 57,
            "capslock": 57,
            "option": 58,
            "alt": 58,
            "alt_r": 61,
            "ctrl": 59,
            "control": 59,
            "ctrl_r": 62,
            "left": 123,
            "right": 124,
            "down": 125,
            "up": 126,
            "page_up": 116,
            "page_down": 121,
            "home": 115,
            "end": 119,
            "f1": 122,
            "f2": 120,
            "f3": 99,
            "f4": 118,
            "f5": 96,
            "f6": 97,
            "f7": 98,
            "f8": 100,
            "f9": 101,
            "f10": 109,
            "f11": 103,
            "f12": 111,
        }

def _build_pynput_key_map(keyboard_module) -> Dict[str, Any]:
    key_map: Dict[str, Any] = {}
    Key = keyboard_module.Key

    def register(names, attr: str) -> None:
        key_obj = getattr(Key, attr, None)
        if key_obj is None:
            return
        for name in names:
            key_map[name] = key_obj

    register(["shift", "shift_l", "shift_r"], "shift")
    register(["ctrl", "ctrl_l", "ctrl_r"], "ctrl")
    register(["alt", "alt_l", "alt_r", "option"], "alt")
    register(["cmd", "cmd_l", "cmd_r", "command", "super"], "cmd")
    register(["enter", "return"], "enter")
    register(["esc", "escape"], "esc")
    register(["space"], "space")
    register(["tab"], "tab")
    register(["backspace"], "backspace")
    register(["delete"], "delete")
    register(["caps_lock"], "caps_lock")
    register(["page_up"], "page_up")
    register(["page_down"], "page_down")
    register(["home"], "home")
    register(["end"], "end")
    register(["up"], "up")
    register(["down"], "down")
    register(["left"], "left")
    register(["right"], "right")

    for fn in range(1, 25):
        attr = f"f{fn}"
        key_obj = getattr(Key, attr, None)
        if key_obj is not None:
            key_map[attr] = key_obj

    return key_map


class EventApplier:
    def __init__(self, send_callback: Callable[[Dict[str, Any]], None]) -> None:
        mouse_module, keyboard_module = import_pynput()
        self._mouse_module = mouse_module
        self._keyboard_module = keyboard_module
        self._mouse = mouse_module.Controller()
        self._keyboard = keyboard_module.Controller()
        self._key_lookup = _build_pynput_key_map(keyboard_module)
        self._pressed_keys: Dict[str, Any] = {}
        self._pressed_buttons: set[Any] = set()
        self._screen_size: Optional[Tuple[int, int]] = None
        self._send = send_callback
        self._session_active = False
        self._session_edge: Optional[str] = None
        self._release_edge: Optional[str] = None
        self._auto_return = False
        self._return_margin = 8
        self._edge_exit_sent = False
        self._cursor = CursorAdapter(mouse_module)
        self._mac_sender: Optional[_MacEventSender] = None
        if sys.platform == "darwin":  # pragma: no cover - mac-only
            try:
                self._mac_sender = _MacEventSender(self._cursor)
            except Exception as exc:
                LOG.debug("macOS event sender unavailable; using pynput fallback (%s)", exc)
                self._mac_sender = None

    def handle(self, event: Dict) -> None:
        etype = event.get("type")
        if etype == "move":
            self._move(event)
        elif etype == "move_to":
            self._move_to(event)
        elif etype == "move_to_edge":
            self._move_to_edge(event)
        elif etype == "click":
            self._click(event)
        elif etype == "scroll":
            self._scroll(event)
        elif etype == "key":
            self._key(event)
        elif etype == "session":
            self._session_event(event)
        elif etype == "heartbeat":
            pass
        else:
            LOG.debug("Ignoring unknown event: %s", event)

    def reset(self) -> None:
        for token, key_obj in list(self._pressed_keys.items()):
            try:
                if key_obj is None:
                    if self._mac_sender is not None:
                        self._mac_sender.key_event(token, False)
                else:
                    self._keyboard.release(key_obj)
            except Exception:
                pass
        self._pressed_keys.clear()

        for button in list(self._pressed_buttons):
            try:
                self._mouse.release(button)
            except Exception:
                pass
        self._pressed_buttons.clear()
        self._session_active = False
        self._release_edge = None
        self._session_edge = None
        self._auto_return = False
        self._edge_exit_sent = False

    def _move(self, event: Dict) -> None:
        dx = int(event.get("dx", 0))
        dy = int(event.get("dy", 0))
        if dx or dy:
            handled = False
            if self._mac_sender is not None:
                handled = self._mac_sender.move_rel(dx, dy)
            if not handled:
                try:
                    self._cursor.move_rel(dx, dy)
                except Exception:
                    self._mouse.move(dx, dy)
            self._maybe_auto_return()

    def _move_to(self, event: Dict) -> None:
        x = event.get("x")
        y = event.get("y")
        if x is not None and y is not None:
            px = int(x)
            py = int(y)
            handled = False
            if self._mac_sender is not None:
                handled = self._mac_sender.move_to(px, py)
            if not handled:
                try:
                    self._cursor.move_to(px, py)
                except Exception:
                    self._mouse.position = (px, py)
            self._maybe_auto_return()

    def _move_to_edge(self, event: Dict) -> None:
        edge = event.get("edge")
        try:
            ratio = float(event.get("ratio", 0.5))
        except (TypeError, ValueError):
            ratio = 0.5
        ratio = max(0.0, min(1.0, ratio))

        width, height = self._get_screen_size()
        if width <= 1 or height <= 1:
            return

        if edge == "right":
            x = max(width - 1, 0)
            y = int(ratio * (height - 1))
        elif edge == "left":
            x = 0
            y = int(ratio * (height - 1))
        elif edge == "top":
            x = int(ratio * (width - 1))
            y = 0
        elif edge == "bottom":
            x = int(ratio * (width - 1))
            y = max(height - 1, 0)
        else:
            x = width // 2
            y = height // 2

        handled = False
        if self._mac_sender is not None:
            handled = self._mac_sender.move_to(int(x), int(y))
        if not handled:
            try:
                self._cursor.move_to(int(x), int(y))
            except Exception:
                self._mouse.position = (int(x), int(y))
        self._maybe_auto_return()

    def _click(self, event: Dict) -> None:
        button_name = event.get("button", "left")
        button = getattr(self._mouse_module.Button, button_name, None)
        if button is None:
            button = self._mouse_module.Button.left
        pressed = bool(event.get("pressed", False))
        handled = False
        if self._mac_sender is not None:
            handled = self._mac_sender.click(button_name, pressed)
        if handled:
            return
        if pressed:
            self._mouse.press(button)
            self._pressed_buttons.add(button)
        else:
            self._mouse.release(button)
            self._pressed_buttons.discard(button)

    def _scroll(self, event: Dict) -> None:
        dx = int(event.get("dx", 0))
        dy = int(event.get("dy", 0))
        if dx or dy:
            handled = False
            if self._mac_sender is not None:
                handled = self._mac_sender.scroll(dx, dy)
            if handled:
                return
            self._mouse.scroll(dx, dy)

    def _key(self, event: Dict) -> None:
        token = event.get("key", "")
        if not token:
            return
        pressed = bool(event.get("pressed", False))

        if pressed and self._mac_sender is not None:
            if self._mac_sender.key_event(token, True):
                self._pressed_keys[token] = None
                return
        elif not pressed and self._mac_sender is not None:
            if token in self._pressed_keys and self._pressed_keys[token] is None:
                if self._mac_sender.key_event(token, False):
                    self._pressed_keys.pop(token, None)
                    return

        if pressed:
            key_obj = self._resolve_key(token)
            if key_obj is None:
                return
            self._keyboard.press(key_obj)
            self._pressed_keys[token] = key_obj
        else:
            key_obj = self._pressed_keys.pop(token, None)
            if key_obj is None:
                key_obj = self._resolve_key(token)
            if key_obj is None:
                return
            self._keyboard.release(key_obj)

    def _resolve_key(self, token: str) -> Optional[Any]:
        if token.startswith("<") and token.endswith(">"):
            name = token[1:-1]
            key_obj = self._key_lookup.get(name)
            if key_obj is not None:
                return key_obj
            name = SPECIAL_KEY_MAP.get(name, name)
            key_obj = self._key_lookup.get(name)
            if key_obj is not None:
                return key_obj
            return None

        if len(token) == 1:
            return self._keyboard_module.KeyCode.from_char(token)
        return self._keyboard_module.KeyCode.from_char(token)

    def _get_screen_size(self) -> Tuple[int, int]:
        if self._screen_size is None:
            try:
                width, height = self._cursor.size()
                self._screen_size = (int(width), int(height))
            except Exception:
                self._screen_size = (1920, 1080)
        return self._screen_size

    def _session_event(self, event: Dict) -> None:
        state = event.get("state")
        LOG.info("Session %s", state)
        if state == "start":
            self._session_active = True
            edge = event.get("edge")
            self._session_edge = edge if edge in OPPOSITE_EDGE else None
            release = event.get("release_edge")
            if isinstance(release, str) and release in OPPOSITE_EDGE:
                self._release_edge = release
            elif self._session_edge:
                self._release_edge = OPPOSITE_EDGE.get(self._session_edge)
            else:
                self._release_edge = None
            self._auto_return = bool(event.get("auto_return", True))
            self._return_margin = 8
            margin = event.get("return_margin")
            if margin is not None:
                try:
                    self._return_margin = max(1, int(margin))
                except (TypeError, ValueError):
                    self._return_margin = 8
            else:
                edge_margin = event.get("edge_margin")
                if isinstance(edge_margin, (int, float)):
                    try:
                        self._return_margin = max(1, int(edge_margin))
                    except (TypeError, ValueError):
                        self._return_margin = 8
            self._edge_exit_sent = False
            self._screen_size = None
        elif state == "stop":
            self._session_active = False
            self._edge_exit_sent = False
            self._release_edge = None
            self._session_edge = None
            self._auto_return = False

    def _maybe_auto_return(self) -> None:
        if not self._session_active or not self._auto_return or not self._release_edge:
            return
        try:
            x, y = self._cursor.position()
        except Exception:
            try:
                px, py = self._mouse.position
                x, y = int(px), int(py)
            except Exception:
                return
        width, height = self._get_screen_size()
        margin = max(1, self._return_margin)
        near_edge = False
        ratio = 0.5
        if self._release_edge == "left":
            near_edge = x <= margin
            ratio = y / max(height - 1, 1)
        elif self._release_edge == "right":
            near_edge = x >= max(width - margin, 0)
            ratio = y / max(height - 1, 1)
        elif self._release_edge == "top":
            near_edge = y <= margin
            ratio = x / max(width - 1, 1)
        elif self._release_edge == "bottom":
            near_edge = y >= max(height - margin, 0)
            ratio = x / max(width - 1, 1)
        if not near_edge:
            self._edge_exit_sent = False
            return
        ratio = max(0.0, min(1.0, ratio))
        if self._edge_exit_sent:
            return
        try:
            self._send({"type": "edge_exit", "edge": self._release_edge, "ratio": ratio})
            self._edge_exit_sent = True
        except Exception as exc:
            LOG.debug("Failed to notify client about edge exit: %s", exc)


class FlowServer:
    def __init__(self, host: str, port: int, token: Optional[str]) -> None:
        self.host = host
        self.port = port
        self.token = token
        self._shutdown = threading.Event()

    def serve_forever(self) -> None:
        pyautogui = import_pyautogui()
        pyautogui.FAILSAFE = False

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen(5)
            LOG.info("Server listening on %s:%d", self.host, self.port)
            sock.settimeout(1.0)

            while not self._shutdown.is_set():
                try:
                    client, addr = sock.accept()
                except socket.timeout:
                    continue
                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client, addr, pyautogui),
                    daemon=True,
                )
                thread.start()

            LOG.info("Server shutting down")

    def shutdown(self) -> None:
        self._shutdown.set()

    def _handle_client(self, client: socket.socket, addr, pyautogui) -> None:
        LOG.info("Connection from %s:%s", addr[0], addr[1])
        client.settimeout(15.0)
        writer_lock = threading.Lock()

        with contextlib.closing(client):
            reader = client.makefile("rb")
            writer = client.makefile("wb")

            def send(payload: Dict[str, Any]) -> None:
                data = json_dumps(payload)
                with writer_lock:
                    try:
                        writer.write(data)
                        writer.flush()
                    except OSError as exc:
                        LOG.debug("Failed to send payload to %s: %s", addr, exc)

            controller = EventApplier(send)
            try:
                hello_line = reader.readline()
                if not hello_line:
                    LOG.warning("%s disconnected before handshake", addr)
                    return
                try:
                    hello = json.loads(hello_line.decode("utf-8"))
                except json.JSONDecodeError:
                    LOG.error("Malformed handshake from %s", addr)
                    return
                try:
                    validate_client_hello(hello, self.token)
                except ProtocolError as exc:
                    LOG.warning("Handshake error from %s: %s", addr, exc)
                    send({"type": "error", "reason": "protocol", "message": str(exc)})
                    return
                send(build_server_welcome())

                for line in reader:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        LOG.warning("Discarding malformed payload from %s", addr)
                        continue
                    controller.handle(event)

            except socket.timeout:
                LOG.warning("Timeout from %s", addr)
            except ConnectionResetError:
                LOG.warning("Connection reset by %s", addr)
            except OSError as exc:
                LOG.warning("Socket error from %s: %s", addr, exc)
            finally:
                controller.reset()
                LOG.info("Disconnected %s", addr)
