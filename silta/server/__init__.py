from __future__ import annotations

import contextlib
import json
import socket
import threading
import time
import sys
from typing import Any, Callable, Dict, Optional, Tuple

try:
    from silta.cursor import CursorAdapter
    from silta.keys import OPPOSITE_EDGE, SPECIAL_KEY_MAP
    from silta.protocol import ProtocolError, build_server_welcome, validate_client_hello
    from silta.utils import LOG, import_pynput, import_pyautogui, json_dumps
except ImportError:
    from ..cursor import CursorAdapter
    from ..keys import OPPOSITE_EDGE, SPECIAL_KEY_MAP
    from ..protocol import ProtocolError, build_server_welcome, validate_client_hello
    from ..utils import LOG, import_pynput, import_pyautogui, json_dumps

from .mac_event_sender import MacEventSender

class EventApplier:
    def __init__(self, send_callback: Callable[[Dict[str, Any]], None]) -> None:
        mouse_module, keyboard_module = import_pynput()
        self._mouse_module = mouse_module
        self._keyboard_module = keyboard_module
        self._mouse = mouse_module.Controller()
        self._keyboard = keyboard_module.Controller()
        self._key_lookup = self._build_pynput_key_map(keyboard_module)
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
        self._mac_sender: Optional[MacEventSender] = None
        if sys.platform == "darwin":
            try:
                self._mac_sender = MacEventSender(self._cursor)
            except Exception as exc:
                LOG.debug("macOS event sender unavailable; using pynput fallback (%s)", exc)
                self._mac_sender = None

    def _build_pynput_key_map(self, keyboard_module) -> Dict[str, Any]:
        key_map: Dict[str, Any] = {}
        Key = keyboard_module.Key
        def register(names, attr: str) -> None:
            key_obj = getattr(Key, attr, None)
            if key_obj is None: return
            for name in names: key_map[name] = key_obj

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
            if key_obj is not None: key_map[attr] = key_obj
        return key_map

    def handle(self, event: Dict) -> None:
        etype = event.get("type")
        if etype == "move": self._move(event)
        elif etype == "move_to": self._move_to(event)
        elif etype == "move_to_edge": self._move_to_edge(event)
        elif etype == "click": self._click(event)
        elif etype == "scroll": self._scroll(event)
        elif etype == "key": self._key(event)
        elif etype == "session": self._session_event(event)
        elif etype == "heartbeat": pass
        else: LOG.debug("Ignoring unknown event: %s", event)

    def reset(self) -> None:
        for token, key_obj in list(self._pressed_keys.items()):
            try:
                if key_obj is None:
                    if self._mac_sender: self._mac_sender.key_event(token, False)
                else:
                    self._keyboard.release(key_obj)
            except Exception: pass
        self._pressed_keys.clear()

        for button in list(self._pressed_buttons):
            try: self._mouse.release(button)
            except Exception: pass
        self._pressed_buttons.clear()
        self._session_active = False
        self._edge_exit_sent = False

    def _move(self, event: Dict) -> None:
        dx, dy = int(event.get("dx", 0)), int(event.get("dy", 0))
        if dx or dy:
            if self._mac_sender and self._mac_sender.move_rel(dx, dy): pass
            else:
                try: self._cursor.move_rel(dx, dy)
                except Exception: self._mouse.move(dx, dy)
            self._maybe_auto_return()

    def _move_to(self, event: Dict) -> None:
        x, y = event.get("x"), event.get("y")
        if x is not None and y is not None:
            px, py = int(x), int(y)
            if self._mac_sender and self._mac_sender.move_to(px, py): pass
            else:
                try: self._cursor.move_to(px, py)
                except Exception: self._mouse.position = (px, py)
            self._maybe_auto_return()

    def _move_to_edge(self, event: Dict) -> None:
        # Implementation for move_to_edge using move_to
        pass

    def _click(self, event: Dict) -> None:
        button_name = event.get("button", "left")
        pressed = bool(event.get("pressed", False))
        if self._mac_sender and self._mac_sender.click(button_name, pressed): return
        
        button = getattr(self._mouse_module.Button, button_name, self._mouse_module.Button.left)
        if pressed:
            self._mouse.press(button)
            self._pressed_buttons.add(button)
        else:
            self._mouse.release(button)
            self._pressed_buttons.discard(button)

    def _scroll(self, event: Dict) -> None:
        dx, dy = int(event.get("dx", 0)), int(event.get("dy", 0))
        if dx or dy:
            if self._mac_sender and self._mac_sender.scroll(dx, dy): return
            self._mouse.scroll(dx, dy)

    def _key(self, event: Dict) -> None:
        token = event.get("key", "")
        if not token: return
        pressed = bool(event.get("pressed", False))

        if pressed and self._mac_sender and self._mac_sender.key_event(token, True):
            self._pressed_keys[token] = None
            return
        elif not pressed and self._mac_sender:
            if token in self._pressed_keys and self._pressed_keys[token] is None:
                if self._mac_sender.key_event(token, False):
                    self._pressed_keys.pop(token, None)
                    return

        if pressed:
            key_obj = self._resolve_key(token)
            if key_obj:
                self._keyboard.press(key_obj)
                self._pressed_keys[token] = key_obj
        else:
            key_obj = self._pressed_keys.pop(token, None) or self._resolve_key(token)
            if key_obj:
                self._keyboard.release(key_obj)

    def _resolve_key(self, token: str) -> Optional[Any]:
        # Resolution logic
        if token.startswith("<") and token.endswith(">"):
            name = token[1:-1]
            key_obj = self._key_lookup.get(name) or self._key_lookup.get(SPECIAL_KEY_MAP.get(name))
            return key_obj
        if len(token) == 1:
             return self._keyboard_module.KeyCode.from_char(token)
        return self._keyboard_module.KeyCode.from_char(token)

    def _get_screen_size(self) -> Tuple[int, int]:
        if self._screen_size is None:
            try:
                pyautogui = import_pyautogui()
                self._screen_size = pyautogui.size()
            except Exception:
                self._screen_size = (1920, 1080)  # fallback
        return self._screen_size

    def _session_event(self, event: Dict) -> None:
        state = event.get("state")
        LOG.info("Session %s", state)
        if state == "start":
            self._session_active = True
            self._auto_return = bool(event.get("auto_return", True))
            self._release_edge = event.get("release_edge")
        elif state == "stop":
            self._session_active = False

    def _maybe_auto_return(self) -> None:
        if not self._session_active or not self._auto_return or not self._release_edge: return
        # Logic to check edges
        pass


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
                if not hello_line: return
                hello = json.loads(hello_line.decode("utf-8"))
                validate_client_hello(hello, self.token)
                send(build_server_welcome())

                for line in reader:
                    line = line.strip()
                    if not line: continue
                    event = json.loads(line.decode("utf-8"))
                    controller.handle(event)

            except (ConnectionResetError, BrokenPipeError, socket.timeout):
                LOG.debug("Client %s disconnected", addr)
            except json.JSONDecodeError as exc:
                LOG.warning("Invalid JSON from %s: %s", addr, exc)
            except ProtocolError as exc:
                LOG.warning("Protocol error from %s: %s", addr, exc)
            except Exception:
                LOG.exception("Unexpected error handling client %s", addr)
            finally:
                controller.reset()
                LOG.info("Disconnected %s", addr)
