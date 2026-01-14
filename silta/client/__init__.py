from __future__ import annotations

import contextlib
import json
import re
import socket
import threading
import time
from typing import Any, Dict, Optional, Tuple
import sys

# Adjust imports for new package structure
# silta.cursor is still at silta/cursor.py? Yes, I haven't moved cursor.py.
# But inside silta/client/, "from .cursor" fails unless cursor is in silta/client/.
# "from ..cursor" should work.
# However, "silta.cursor" is cleaner.
try:
    from silta.cursor import CursorAdapter
    from silta.keys import OPPOSITE_EDGE, format_key
    from silta.local_cursor import LocalCursorManager
    from silta.protocol import ProtocolError, build_client_hello, validate_server_welcome
    from silta.utils import LOG, ConnectionError, import_pyautogui, import_pynput, json_dumps
except ImportError:
    # Fallback if run directly or during development
    from ..cursor import CursorAdapter
    from ..keys import OPPOSITE_EDGE
    from ..local_cursor import LocalCursorManager
    from ..protocol import ProtocolError, build_client_hello, validate_server_welcome
    from ..utils import LOG, ConnectionError, import_pyautogui, import_pynput, json_dumps

from .mac_event_tap import MacEventTap, EventSink

if sys.platform == "darwin":
    DEFAULT_TOGGLE_HOTKEY = "<cmd>+<option>+f"
    DEFAULT_BACK_HOTKEY = "<cmd>+<option>+d"
else:
    DEFAULT_TOGGLE_HOTKEY = "<ctrl>+<alt>+f"
    DEFAULT_BACK_HOTKEY = "<ctrl>+<alt>+d"


ServerTarget = Tuple[str, int, Optional[str]]


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

        self._toggle_hotkey = None
        self._back_hotkey = None

        # macOS Event Tap
        self._mac_tap: Optional[MacEventTap] = None
        if sys.platform == "darwin":
            self._mac_tap = MacEventTap(self, self._keyboard)


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

        def toggle_cb():
            self.activate_remote("hotkey")
        
        def back_cb():
            self.deactivate_remote()

        toggle = self._keyboard.HotKey(
            self._parse_hotkey(self.toggle_hotkey, DEFAULT_TOGGLE_HOTKEY),
            toggle_cb,
        )
        back = self._keyboard.HotKey(
            self._parse_hotkey(self.back_hotkey, DEFAULT_BACK_HOTKEY),
            back_cb,
        )

        self._toggle_hotkey = toggle
        self._back_hotkey = back

        # Start listeners
        started = False
        if self._mac_tap:
            started = self._mac_tap.start()
            
        if started:
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
            # Pynput fallback
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
        if self._mac_tap:
            self._mac_tap.stop()
            
        self._reset_connection_state()
        if self._connection_thread and self._connection_thread.is_alive():
            self._connection_thread.join(timeout=2.0)
        for t in threads:
            if t.is_alive():
                t.join(timeout=1.0)

    # --- EventSink Protocol Implementation ---
    def on_move(self, x: int, y: int) -> None:
        self._on_move(x, y)
        
    def on_click(self, x: int, y: int, button: Any, pressed: bool) -> None:
        self._on_click(x, y, button, pressed)
        
    def on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        self._on_scroll(x, y, dx, dy)
        
    def on_press(self, key: Any) -> None:
        self._on_press(key)
        
    def on_release(self, key: Any) -> None:
        self._on_release(key)
        
    def is_remote_active(self) -> bool:
        return self._remote_active.is_set()
        
    def get_hotkeys(self) -> Tuple[Any, Any]:
        return (self._toggle_hotkey, self._back_hotkey)

    # --- Event Handlers (Legacy + Protocol) ---
    def _on_move(self, x: int, y: int) -> None:
        self._last_mouse_pos = (x, y)
        if not self._remote_active.is_set():
            return
        self._send({"type": "move_to", "x": x, "y": y})

    def _on_click(self, x: int, y: int, button, pressed: bool) -> None:
        if not self._remote_active.is_set():
            return
        btn_name = getattr(button, "name", "left")
        self._send({"type": "click", "button": btn_name, "pressed": pressed})

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if not self._remote_active.is_set():
            return
        self._send({"type": "scroll", "dx": dx, "dy": dy})

    def _on_press(self, key) -> None:
        if not self._remote_active.is_set():
            return
        self._send({"type": "key", "key": format_key(key), "pressed": True})

    def _on_release(self, key) -> None:
        if not self._remote_active.is_set():
            return
        self._send({"type": "key", "key": format_key(key), "pressed": False})


    
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
                edge_label, profile[0], profile[1]
            )
            return False
        return True

    def _switch_server(self, profile: ServerTarget) -> None:
        current = self._current_server_target()
        if current == profile and not self._connected.is_set():
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

    def _connection_loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            if self._reconnect.is_set():
                with self._pending_lock:
                    pending = self._pending_server
                    self._pending_server = None
                self._reconnect.clear()
                if pending:
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
                with contextlib.suppress(Exception): writer.close()
                with contextlib.suppress(Exception): reader.close()
                with contextlib.suppress(Exception): sock.close()

    def _reader_worker(self) -> None:
        while not self._stop.is_set():
            with self._connection_lock:
                reader = self._reader
            if reader is None: return
            try:
                line = reader.readline()
            except OSError as exc:
                if self._stop.is_set(): return
                raise ConnectionError(f"Error reading from server: {exc}") from exc
            if not line: raise ConnectionError("Server closed the connection")
            try:
                message = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                LOG.debug("Discarding malformed message from server")
                continue
            self._handle_server_message(message)

    def _send(self, payload: Dict) -> None:
        if not self._connected.is_set(): raise ConnectionError("Not connected to server")
        with self._connection_lock:
            connection = self._connection
            writer = self._writer
        if not connection or not writer: raise ConnectionError("Not connected to server")
        data = json_dumps(payload)
        with self._writer_lock:
            try:
                writer.write(data)
                writer.flush()
            except OSError as exc:
                raise ConnectionError("Failed to send payload") from exc

    def _reset_connection_state(self) -> None:
        with self._connection_lock:
            sock, reader, writer = self._connection, self._reader, self._writer
            self._connection = self._reader = self._writer = None
        if writer:
            with contextlib.suppress(Exception): writer.close()
        if reader:
            with contextlib.suppress(Exception): reader.close()
        if sock:
            with contextlib.suppress(OSError): sock.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(Exception): sock.close()

    def _handle_server_message(self, message: Dict[str, Any]) -> None:
        mtype = message.get("type")
        if mtype == "edge_exit":
            if not self.auto_return or not self._remote_active.is_set(): return
            ratio_value = message.get("ratio", 0.5)
            release_edge = message.get("edge")
            if isinstance(release_edge, str) and release_edge in OPPOSITE_EDGE:
                self._last_auto_edge = OPPOSITE_EDGE[release_edge]
            LOG.info("Remote requested return via %s edge (ratio=%.3f)", message.get("edge"), float(ratio_value) if isinstance(ratio_value, (int, float)) else 0.5)
            edge_data = {"edge": message.get("edge"), "ratio": ratio_value}
            self.deactivate_remote(reason="edge_exit", edge_data=edge_data)
        elif mtype == "error":
            LOG.error("Server reported error: %s (%s)", message.get("reason"), message.get("message"))
        else:
            LOG.debug("Ignoring message from server: %s", message)

    def activate_remote(self, reason: str, edge_override: Optional[str] = None) -> None:
        if self._remote_active.is_set(): return
        edge_for_session = self._resolve_active_edge(edge_override)
        if not self._ensure_connection_for_edge(edge_for_session):
            LOG.warning("Remote session aborted: server unavailable for edge '%s'", edge_for_session or "default")
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
            payload: Dict[str, Any] = {
                "type": "session", "state": "start", "reason": reason,
                "auto_return": self.auto_return, "return_margin": self.return_margin,
                "edge_margin": self.edge_margin
            }
            if edge_for_session:
                payload["edge"] = edge_for_session
                self._active_edge = edge_for_session
                self._last_auto_edge = edge_for_session
            if release_edge:
                payload["release_edge"] = release_edge
            self._send(payload)
        except ConnectionError as exc:
            LOG.error("Unable to start remote session: %s", exc)
            self._remote_active.clear()
            return
            
        self._cursor_manager.start_remote_session()

    def deactivate_remote(self, reason: str = "user", notify_server: bool = True, edge_data: Optional[Dict] = None) -> None:
        if not self._remote_active.is_set(): return
        LOG.info("Remote session ending (%s)", reason)
        self._remote_active.clear()
        
        if notify_server and self._connected.is_set():
            try:
                payload = {"type": "session", "state": "stop", "reason": reason}
                if edge_data: payload.update(edge_data)
                self._send(payload)
            except ConnectionError: pass
            
        self._cursor_manager.stop_remote_session()
        # Restore cursor if needed
        if edge_data:
             self._place_cursor_from_edge(edge_data)
        else:
             self._center_cursor()

    def _place_cursor_from_edge(self, edge_data: Dict) -> None:
        try:
            width, height = self._cursor_adapter.size()
            edge = edge_data.get("edge")
            ratio = float(edge_data.get("ratio", 0.5))
            if edge == "left":
                x, y = 10, height * ratio
            elif edge == "right":
                x, y = width - 10, height * ratio
            elif edge == "top":
                x, y = width * ratio, 10
            elif edge == "bottom":
                x, y = width * ratio, height - 10
            else:
                x, y = width // 2, height // 2
            self._cursor_adapter.move_to(int(x), int(y))
        except Exception: pass

    def _center_cursor(self) -> None:
        try:
            width, height = self._cursor_adapter.size()
            self._cursor_adapter.move_to(width // 2, height // 2)
        except Exception: pass

    def _resolve_active_edge(self, edge_override: Optional[str]) -> Optional[str]:
        if edge_override: return edge_override
        if self._last_auto_edge: return self._last_auto_edge
        return self.edge

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(self.heartbeat)
            if self._connected.is_set() and self._remote_active.is_set():
                try:
                    self._send({"type": "heartbeat"})
                except ConnectionError: pass

    def _edge_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(self.edge_delay)
            if self._remote_active.is_set(): continue
            if not self._connected.is_set() and not self._reconnect.is_set():
                # Try background reconnect
                 pass
            
            try:
                current_pos = self._cursor_adapter.position()
                self._check_edges(current_pos)
            except Exception: pass

    def _check_edges(self, pos: Tuple[int, int]) -> None:
        # Check against active edges in _edge_profiles
        pass
        
    def _parse_hotkey(self, hotkey: str, default: str) -> str:
        # Parse logic
        return hotkey or default

