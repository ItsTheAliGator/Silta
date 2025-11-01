from __future__ import annotations

import json
import logging
from typing import Any, Dict, Tuple

LOG = logging.getLogger("silta")


class ConnectionError(Exception):
    """Raised when the client cannot communicate with the server."""


class DependencyError(RuntimeError):
    """Raised when an optional runtime dependency is missing."""


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s: %(message)s",
    )


def json_dumps(obj: Dict) -> bytes:
    return (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")


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
