from __future__ import annotations

from typing import Dict, Any, Optional

class MacEventSender:
    def __init__(self, cursor_adapter) -> None:
        import Quartz.CoreGraphics as CG  # type: ignore
        self._cursor = cursor_adapter
        self._CG = CG
        self._source = CG.CGEventSourceCreate(CG.kCGEventSourceStateCombinedSessionState)
        self._char_keycodes = self._build_char_keycodes()
        self._special_keycodes = self._build_special_keycodes()

    def move_rel(self, dx: int, dy: int) -> bool:
        if dx == 0 and dy == 0: return True
        try:
            x, y = self._cursor.position()
        except Exception: return False
        return self.move_to(x + dx, y + dy)

    def move_to(self, x: int, y: int) -> bool:
        CG = self._CG
        event = CG.CGEventCreateMouseEvent(
            self._source, CG.kCGEventMouseMoved, (float(x), float(y)), CG.kCGMouseButtonLeft
        )
        if not event: return False
        CG.CGEventPost(CG.kCGHIDEventTap, event)
        return True

    def click(self, button_name: str, pressed: bool) -> bool:
        CG = self._CG
        button_map = {"left": CG.kCGMouseButtonLeft, "right": CG.kCGMouseButtonRight, "middle": 2}
        button = button_map.get(button_name, CG.kCGMouseButtonLeft)
        try:
            x, y = self._cursor.position()
        except Exception: return False
        
        event_type = None
        if button == CG.kCGMouseButtonLeft:
            event_type = CG.kCGEventLeftMouseDown if pressed else CG.kCGEventLeftMouseUp
        elif button == CG.kCGMouseButtonRight:
            event_type = CG.kCGEventRightMouseDown if pressed else CG.kCGEventRightMouseUp
        else:
            event_type = CG.kCGEventOtherMouseDown if pressed else CG.kCGEventOtherMouseUp
            
        event = CG.CGEventCreateMouseEvent(self._source, event_type, (float(x), float(y)), button)
        if not event: return False
        CG.CGEventPost(CG.kCGHIDEventTap, event)
        return True

    def scroll(self, dx: int, dy: int) -> bool:
        CG = self._CG
        event = CG.CGEventCreateScrollWheelEvent(self._source, CG.kCGScrollEventUnitLine, 2, int(dy), int(dx))
        if not event: return False
        CG.CGEventPost(CG.kCGHIDEventTap, event)
        return True

    def key_event(self, token: str, pressed: bool) -> bool:
        CG = self._CG
        keycode = None
        if token.startswith("<") and token.endswith(">"):
            name = token[1:-1].lower()
            keycode = self._special_keycodes.get(name)
        else:
            keycode = self._char_keycodes.get(token.lower())
        
        if keycode is None: return False
        event = CG.CGEventCreateKeyboardEvent(self._source, keycode, pressed)
        if not event: return False
        if len(token) == 1:
            CG.CGEventKeyboardSetUnicodeString(event, 1, token)
        CG.CGEventPost(CG.kCGHIDEventTap, event)
        return True

    def _build_char_keycodes(self) -> Dict[str, int]:
        return {
            "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
            "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19,
            "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28,
            "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37, "j": 38,
            "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, "`": 50
        }

    def _build_special_keycodes(self) -> Dict[str, int]:
        return {
            "return": 36, "enter": 36, "tab": 48, "space": 49, "backspace": 51, "delete": 117,
            "esc": 53, "escape": 53, "cmd": 55, "command": 55, "shift": 56, "caps_lock": 57,
            "option": 58, "alt": 58, "ctrl": 59, "control": 59, "right": 124, "left": 123,
            "down": 125, "up": 126
        }
