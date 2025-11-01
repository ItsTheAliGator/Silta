from __future__ import annotations

"""Display information helpers for macOS (read-only).

Collects friendly names, resolution, scale factor, refresh rate, and topology
using AppKit (NSScreen) and Quartz/CoreGraphics. Designed to be App Store–safe
and avoid private APIs or write operations.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DisplayInfo:
    id: int
    name: Optional[str]
    is_builtin: bool
    is_main: bool
    is_mirrored: bool
    pixels_w: int
    pixels_h: int
    scale: float
    refresh_hz: Optional[float]
    max_fps: Optional[int]
    rotation: int


def _import_appkit_quartz():
    try:
        import AppKit  # type: ignore
        import Quartz  # type: ignore
        return AppKit, Quartz
    except Exception as exc:  # pragma: no cover - mac-only
        raise RuntimeError(
            "DisplayInfo requires PyObjC (AppKit, Quartz) on macOS"
        ) from exc


def get_displays() -> List[DisplayInfo]:
    AppKit, Quartz = _import_appkit_quartz()

    screens = AppKit.NSScreen.screens()
    results: List[DisplayInfo] = []

    for screen in screens or []:
        desc = screen.deviceDescription()
        display_id = int(desc.get("NSScreenNumber", 0))
        if display_id == 0:
            continue

        name = None
        if hasattr(screen, "localizedName"):
            try:
                name = str(screen.localizedName())
            except Exception:  # pragma: no cover - older macOS
                name = None

        # Dimensions
        pixels_w = int(Quartz.CGDisplayPixelsWide(display_id))
        pixels_h = int(Quartz.CGDisplayPixelsHigh(display_id))

        # Scale factor
        try:
            scale = float(screen.backingScaleFactor())
        except Exception:  # pragma: no cover - fallback
            scale = 1.0

        # Refresh rate: fixed panels return a number; VRR panels may return 0.
        refresh_hz: Optional[float] = None
        try:
            mode = Quartz.CGDisplayCopyDisplayMode(display_id)
            if mode is not None:
                rr = float(Quartz.CGDisplayModeGetRefreshRate(mode))
                if rr > 0:
                    refresh_hz = rr
        except Exception:
            pass

        # Max FPS for VRR/ProMotion hints
        max_fps: Optional[int] = None
        if hasattr(screen, "maximumFramesPerSecond"):
            try:
                val = int(screen.maximumFramesPerSecond())
                if val > 0:
                    max_fps = val
            except Exception:
                pass

        is_builtin = bool(Quartz.CGDisplayIsBuiltin(display_id))
        is_main = bool(Quartz.CGDisplayIsMain(display_id))
        is_mirrored = bool(Quartz.CGDisplayIsInMirrorSet(display_id))
        rotation = int(Quartz.CGDisplayRotation(display_id))

        results.append(
            DisplayInfo(
                id=display_id,
                name=name,
                is_builtin=is_builtin,
                is_main=is_main,
                is_mirrored=is_mirrored,
                pixels_w=pixels_w,
                pixels_h=pixels_h,
                scale=scale,
                refresh_hz=refresh_hz,
                max_fps=max_fps,
                rotation=rotation,
            )
        )

    return results
