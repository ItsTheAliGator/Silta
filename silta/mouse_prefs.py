from __future__ import annotations

"""Mouse preference helpers for macOS.

Reads the current mouse speed (acceleration scalar) from the global
preferences in a sandbox-safe way via CoreFoundation. Falls back to
invoking `defaults read -g com.apple.mouse.scaling` when CFPreferences
is not available.
"""

from typing import Optional


def _read_via_cfpreferences() -> Optional[float]:  # pragma: no cover - mac-only
    try:
        import CoreFoundation  # type: ignore
    except Exception:
        return None
    key = "com.apple.mouse.scaling"
    # Global preferences domain. Both "NSGlobalDomain" and ".GlobalPreferences" are used
    # historically; CFPreferences prefers the latter.
    domain = ".GlobalPreferences"
    try:
        value = CoreFoundation.CFPreferencesCopyAppValue(key, domain)
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _read_via_defaults() -> Optional[float]:  # pragma: no cover - shell fallback
    import subprocess

    try:
        out = subprocess.check_output(
            [
                "/usr/bin/defaults",
                "read",
                "-g",
                "com.apple.mouse.scaling",
            ],
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None
    try:
        return float(out.decode("utf-8").strip())
    except Exception:
        return None


def read_mouse_speed() -> Optional[float]:
    """Return the current mouse speed scalar, or None if unavailable."""

    val = _read_via_cfpreferences()
    if val is not None:
        return val
    return _read_via_defaults()
