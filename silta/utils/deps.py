from typing import Any, Tuple

from .errors import DependencyError

def import_pyautogui() -> Any:
    try:
        import pyautogui  # type: ignore

        pyautogui.PAUSE = 0
        pyautogui.MINIMUM_DURATION = 0
        pyautogui.MINIMUM_SLEEP = 0
        return pyautogui
    except ImportError as exc:  # pragma: no cover
        raise DependencyError(
            "pyautogui is required. Install it with: python3 -m pip install --user pyautogui"
        ) from exc


def import_pynput() -> Tuple[Any, Any]:
    try:
        from pynput import keyboard, mouse  # type: ignore

        return mouse, keyboard
    except ImportError as exc:  # pragma: no cover
        raise DependencyError(
            "pynput is required on the controller machine. Install it with: python3 -m pip install --user pynput"
        ) from exc
