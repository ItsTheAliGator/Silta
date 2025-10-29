from __future__ import annotations

from typing import Any, Dict, Optional


SPECIAL_KEY_MAP = {
    "shift": "shift",
    "shift_l": "shift",
    "shift_r": "shift",
    "ctrl": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "alt": "alt",
    "alt_l": "alt",
    "alt_r": "alt",
    "option": "alt",
    "cmd": "command",
    "cmd_l": "command",
    "cmd_r": "command",
    "super": "command",
    "enter": "enter",
    "return": "enter",
    "esc": "esc",
    "escape": "esc",
    "space": "space",
    "tab": "tab",
    "backspace": "backspace",
    "delete": "delete",
    "caps_lock": "capslock",
    "page_up": "pageup",
    "page_down": "pagedown",
    "home": "home",
    "end": "end",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
}

OPPOSITE_EDGE = {
    "left": "right",
    "right": "left",
    "top": "bottom",
    "bottom": "top",
}


def format_key(key) -> Optional[str]:
    try:
        return key.char  # type: ignore[attr-defined]
    except AttributeError:
        name = getattr(key, "name", str(key))
        if name.startswith("Key."):
            name = name.split(".", 1)[1]
        return f"<{name}>"


def translate_key_for_pyautogui(key: str) -> str:
    if key.startswith("<") and key.endswith(">"):
        name = key[1:-1]
        return SPECIAL_KEY_MAP.get(name, name)
    return key
