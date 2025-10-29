from __future__ import annotations

from typing import Any, Optional, Tuple

from .cursor import CursorAdapter, hide_system_cursor, show_system_cursor
from .utils import LOG


class LocalCursorManager:
    def __init__(self, mouse_module, mode: str) -> None:
        self.mode = mode
        self._mouse_module = mouse_module
        self._hidden = False
        self._controller = None
        self._cursor = CursorAdapter(mouse_module)
        self._frozen = False

    def on_remote_start(self, edge: Optional[str], edge_margin: int) -> None:
        if self.mode == "visible":
            return
        if not self._frozen:
            self._frozen = self._cursor.freeze_cursor(True) or self._frozen
        if self.mode in {"auto", "hide"}:
            hidden = hide_system_cursor()
            LOG.debug("Local cursor hide attempt: mode=%s success=%s", self.mode, hidden)
            if hidden:
                self._hidden = True
                return
            if self.mode == "hide":
                return
        if self.mode in {"auto", "warp"}:
            LOG.debug("Warping local cursor away from edge (mode=%s, edge=%s)", self.mode, edge)
            self._warp_cursor(edge, edge_margin)

    def on_remote_stop(self) -> None:
        if self._hidden:
            show_system_cursor()
            self._hidden = False
        if self._frozen and self._cursor.freeze_cursor(False):
            self._frozen = False

    def _warp_cursor(self, edge: Optional[str], edge_margin: int) -> None:
        try:
            if not self._controller:
                self._controller = self._mouse_module.Controller()
            controller = self._controller
            x, y = controller.position
            target = self._calculate_target(edge, (x, y), edge_margin)
            controller.position = target
        except Exception:
            pass

    def _calculate_target(self, edge: Optional[str], pos: Tuple[int, int], margin: int) -> Tuple[int, int]:
        x, y = pos
        try:
            width, height = self._cursor.size()
        except Exception:
            return int(x), int(y)

        if edge == "right":
            target_x = max(int(width) - margin, 0)
            target_y = max(0, min(int(y), int(height) - 1))
        elif edge == "left":
            target_x = min(margin, max(int(width) - 1, 0))
            target_y = max(0, min(int(y), int(height) - 1))
        elif edge == "top":
            target_x = max(0, min(int(x), int(width) - 1))
            target_y = min(margin, max(int(height) - 1, 0))
        elif edge == "bottom":
            target_x = max(0, min(int(x), int(width) - 1))
            target_y = max(int(height) - margin, 0)
        else:
            target_x = int(width) // 2
            target_y = int(height) // 2

        try:
            self._cursor.move_to(int(target_x), int(target_y))
            return int(target_x), int(target_y)
        except Exception:
            return int(x), int(y)
