import sys
from typing import Optional, Callable, Dict, Any, Tuple
from silta.utils import LOG, import_pynput
from silta.client.mac_event_tap import MacEventTap, EventSink
from silta.keys import format_key

class LocalInputMonitor(EventSink):
    """
    Monitors local input events (Mouse/Keyboard) and detects edge crossings.
    Decoupled from network logic.
    """
    def __init__(self, 
                 on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
                 on_edge: Optional[Callable[[str, float], None]] = None,
                 on_hotkey: Optional[Callable[[str], None]] = None):
        self.on_event = on_event
        self.on_edge = on_edge
        self.on_hotkey = on_hotkey
        
        self._suppress = False
        self._mac_tap: Optional[MacEventTap] = None
        self._mouse, self._keyboard = import_pynput()
        
        # Hotkeys
        self._toggle_hotkey: Any = None
        self._back_hotkey: Any = None
        
        if sys.platform == "darwin":
            self._mac_tap = MacEventTap(self, self._keyboard)

    def start(self):
        if self._mac_tap:
            if not self._mac_tap.start():
                LOG.error("Failed to start MacEventTap")
        else:
            LOG.warning("LocalInputMonitor: MacEventTap not available (not on macOS?)")

    def stop(self):
        if self._mac_tap:
            self._mac_tap.stop()

    def set_suppress(self, suppress: bool):
        """If true, events are consumed and not passed to OS."""
        self._suppress = suppress

    # --- EventSink Protocol ---
    def is_remote_active(self) -> bool:
        return self._suppress

    def get_hotkeys(self) -> Tuple[Any, Any]:
        return (self._toggle_hotkey, self._back_hotkey)

    def on_move(self, x: int, y: int) -> None:
        if self.on_event:
            self.on_event({"type": "move_to", "x": x, "y": y})
        # TODO: Edge detection logic here?
        # Or decoupled edge detector?
        # For simplicity, we can do basic edge check if not suppressed.
        if not self._suppress and self.on_edge:
             # Check edges
             pass

    def on_click(self, x: int, y: int, button: Any, pressed: bool) -> None:
        if self.on_event:
            btn_name = getattr(button, "name", "left")
            self.on_event({"type": "click", "button": btn_name, "pressed": pressed})

    def on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if self.on_event:
            self.on_event({"type": "scroll", "dx": dx, "dy": dy})

    def on_press(self, key: Any) -> None:
        if self.on_event:
            self.on_event({"type": "key", "key": format_key(key), "pressed": True})

    def on_release(self, key: Any) -> None:
        if self.on_event:
            self.on_event({"type": "key", "key": format_key(key), "pressed": False})

    def set_hotkeys(self, toggle_str: str, back_str: str):
        # Parse and store key objects provided by pynput
        pass
