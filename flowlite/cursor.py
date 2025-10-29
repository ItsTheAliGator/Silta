from __future__ import annotations

import contextlib
import sys
from typing import Any, Optional, Tuple

from .utils import DependencyError, import_pynput, import_pyautogui


def hide_system_cursor() -> bool:
    if sys.platform == "darwin":
        try:
            import ctypes
            from ctypes import util

            app_services = ctypes.CDLL(util.find_library("ApplicationServices"))
            app_services.CGMainDisplayID.restype = ctypes.c_uint32
            display_id = app_services.CGMainDisplayID()
            app_services.CGDisplayHideCursor.argtypes = [ctypes.c_uint32]
            app_services.CGDisplayHideCursor.restype = ctypes.c_int32
            result = app_services.CGDisplayHideCursor(display_id)
            return result == 0
        except Exception:
            return False
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.user32.ShowCursor(False)
            return True
        except Exception:
            return False
    return False


def show_system_cursor() -> None:
    if sys.platform == "darwin":
        try:
            import ctypes
            from ctypes import util

            app_services = ctypes.CDLL(util.find_library("ApplicationServices"))
            app_services.CGMainDisplayID.restype = ctypes.c_uint32
            display_id = app_services.CGMainDisplayID()
            app_services.CGDisplayShowCursor.argtypes = [ctypes.c_uint32]
            app_services.CGDisplayShowCursor.restype = ctypes.c_int32
            app_services.CGDisplayShowCursor(display_id)
        except Exception:
            pass
    elif sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.user32.ShowCursor(True)
        except Exception:
            pass


_SCREEN_SIZE_CACHE: Optional[Tuple[int, int]] = None


def _screen_size() -> Tuple[int, int]:
    global _SCREEN_SIZE_CACHE
    if _SCREEN_SIZE_CACHE is None:
        _SCREEN_SIZE_CACHE = _probe_screen_size()
    return _SCREEN_SIZE_CACHE


def _probe_screen_size() -> Tuple[int, int]:
    for getter in (
        _quartz_screen_size,
        _pyautogui_screen_size,
        _ctypes_screen_size,
        _tkinter_screen_size,
    ):
        try:
            size = getter()
        except Exception:
            size = None
        if size:
            width, height = size
            if width > 0 and height > 0:
                return int(width), int(height)
    return (1920, 1080)


def _quartz_screen_size() -> Optional[Tuple[int, int]]:
    if sys.platform != "darwin":
        return None
    try:
        import Quartz  # type: ignore

        display = Quartz.CGMainDisplayID()
        width = Quartz.CGDisplayPixelsWide(display)
        height = Quartz.CGDisplayPixelsHigh(display)
        return int(width), int(height)
    except Exception:
        return None


def _pyautogui_screen_size() -> Optional[Tuple[int, int]]:
    try:
        module = import_pyautogui()
    except DependencyError:
        return None
    except RuntimeError:
        return None
    try:
        width, height = module.size()
        return int(width), int(height)
    except Exception:
        return None


def _ctypes_screen_size() -> Optional[Tuple[int, int]]:
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes

        user32 = ctypes.windll.user32
        with contextlib.suppress(Exception):
            user32.SetProcessDPIAware()
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        return int(width), int(height)
    except Exception:
        return None


def _tkinter_screen_size() -> Optional[Tuple[int, int]]:
    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        root.update_idletasks()
        width = root.winfo_screenwidth()
        height = root.winfo_screenheight()
        root.destroy()
        return int(width), int(height)
    except Exception:
        return None


class CursorAdapter:
    """Unified cursor operations with fast macOS support."""

    def __init__(self, mouse_module=None) -> None:
        self._mouse_module = mouse_module
        self._impl = self._select_impl()

    def _select_impl(self):
        factories = []
        if sys.platform == "darwin":
            factories.append(self._make_macos_impl)
        factories.extend([self._make_pyautogui_impl, self._make_pynput_impl])
        last_error = None
        for factory in factories:
            try:
                impl = factory()
                if impl is not None:
                    return impl
            except Exception as exc:  # pragma: no cover - defensive
                last_error = exc
        raise RuntimeError(f"No cursor backend available ({last_error})")

    def _make_macos_impl(self):
        try:
            import Quartz  # type: ignore
        except Exception as exc:  # pragma: no cover - Quartz missing
            raise RuntimeError("Quartz unavailable") from exc
        return _MacCursorImpl(Quartz)

    def _make_pyautogui_impl(self):
        try:
            module = import_pyautogui()
        except SystemExit as exc:
            raise RuntimeError("pyautogui unavailable") from exc
        except Exception as exc:
            raise RuntimeError("pyautogui import failed") from exc
        return _PyAutoCursorImpl(module)

    def _make_pynput_impl(self):
        mouse_module = self._mouse_module
        if mouse_module is None:
            mouse_module, _keyboard = import_pynput()
        return _PynputCursorImpl(mouse_module)

    def position(self) -> Tuple[int, int]:
        return self._impl.position()

    def move_to(self, x: int, y: int) -> None:
        self._impl.move_to(int(x), int(y))

    def move_rel(self, dx: int, dy: int) -> None:
        if dx or dy:
            self._impl.move_rel(int(dx), int(dy))

    def size(self) -> Tuple[int, int]:
        return self._impl.size()

    def freeze_cursor(self, frozen: bool) -> bool:
        impl = self._impl
        handler = getattr(impl, "freeze_cursor", None)
        if not handler:
            return False
        try:
            handler(bool(frozen))
            return True
        except Exception:
            return False


class _MacCursorImpl:
    def __init__(self, quartz_module) -> None:
        self._Quartz = quartz_module
        self._display = self._Quartz.CGMainDisplayID()
        self._frozen = False

    def position(self) -> Tuple[int, int]:
        event = self._Quartz.CGEventCreate(None)
        loc = self._Quartz.CGEventGetLocation(event)
        return int(loc.x), int(loc.y)

    def move_to(self, x: int, y: int) -> None:
        self._Quartz.CGWarpMouseCursorPosition((float(x), float(y)))
        if not self._frozen:
            self._Quartz.CGAssociateMouseAndMouseCursorPosition(True)

    def move_rel(self, dx: int, dy: int) -> None:
        x, y = self.position()
        self.move_to(x + dx, y + dy)

    def size(self) -> Tuple[int, int]:
        width = self._Quartz.CGDisplayPixelsWide(self._display)
        height = self._Quartz.CGDisplayPixelsHigh(self._display)
        return int(width), int(height)

    def freeze_cursor(self, frozen: bool) -> None:
        if bool(frozen) == self._frozen:
            return
        self._Quartz.CGAssociateMouseAndMouseCursorPosition(not frozen)
        self._frozen = bool(frozen)


class _PyAutoCursorImpl:
    def __init__(self, module) -> None:
        self._pyautogui = module
        self._pyautogui.FAILSAFE = False

    def position(self) -> Tuple[int, int]:
        pos = self._pyautogui.position()
        return int(pos[0]), int(pos[1])

    def move_to(self, x: int, y: int) -> None:
        self._pyautogui.moveTo(int(x), int(y))

    def move_rel(self, dx: int, dy: int) -> None:
        self._pyautogui.moveRel(int(dx), int(dy))

    def size(self) -> Tuple[int, int]:
        width, height = self._pyautogui.size()
        return int(width), int(height)


class _PynputCursorImpl:
    def __init__(self, mouse_module) -> None:
        self._mouse_module = mouse_module
        self._controller = None

    def _get_controller(self):
        if not self._controller:
            self._controller = self._mouse_module.Controller()
        return self._controller

    def position(self) -> Tuple[int, int]:
        controller = self._get_controller()
        x, y = controller.position
        return int(x), int(y)

    def move_to(self, x: int, y: int) -> None:
        controller = self._get_controller()
        controller.position = (int(x), int(y))

    def move_rel(self, dx: int, dy: int) -> None:
        controller = self._get_controller()
        controller.move(dx, dy)

    def size(self) -> Tuple[int, int]:
        return _screen_size()
