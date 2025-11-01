# Silta GUI MVP Plan

This living document tracks the plan and progress for a macOS menubar GUI that shows host/device/display information in a read-only way and looks native.

## Scope (MVP)

- Menubar app with a compact info view.
- Show:
  - Mac hostname.
  - Connected keyboard(s)/mouse(s) with capability hints.
  - Displays: internal/external, resolution, refresh rate, scaling factor.
  - Current mouse speed (read-only).
- Read-only device/display interactions; no control commands.
- Built with AppKit via PyObjC; later enhance popover visuals with NSVisualEffectView.

## Architecture

- UI: `silta/menubar.py` (PyObjC AppKit) creates an NSStatusItem and menu for MVP.
- Data providers:
  - `silta/display_info.py` – Enumerate displays using AppKit (NSScreen) and Quartz (CGDisplay\*).
  - `silta/mouse_prefs.py` – Read mouse speed via CoreFoundation CFPreferences; fallback to `defaults`.
  - `silta/mac_hid.py` – Existing ioreg-based device enumeration; used for dev builds. For App Store, will replace with PyObjC IOKit.
  - `silta/capabilities.py` – Map VID/PID to capability hints.
- CLI integration: `silta/cli.py gui` launches the menubar app.

## Tasks and status

- [x] Display info provider (resolution, refresh, scaling, built-in flag) — `silta/display_info.py`.
- [x] Mouse speed reader (CFPreferences, with fallback) — `silta/mouse_prefs.py`.
- [x] Capability mapping for common Logitech MX devices (read-only hints) — `silta/capabilities.py`.
- [x] Menubar UI showing all info — `silta/menubar.py`.
- [x] CLI `gui` command — `silta/cli.py`.
- [x] Optional GUI deps in `pyproject.toml` — extra `gui`.

## Nice-to-haves (post-MVP)

- Replace menu with a popover using NSVisualEffectView for a glass look.
- App Store target: remove subprocess fallbacks; use IOKit via PyObjC for HID.
- Icons for device types and vendors.
- Periodic auto-refresh and change notifications.

## HID capabilities matrix – status

- Implemented:
  - Read-only capability hints are shown in the GUI using `silta/capabilities.py`.
  - Current coverage focuses on common Logitech MX devices (VID 0x046D with selected PIDs) and Unifying receiver.
  - Enumeration currently uses `silta/mac_hid.py` (ioreg subprocess), acceptable for dev builds.
- Gaps:
  - Limited device coverage; some models have multiple PIDs (USB vs Bluetooth variants).
  - Dev enumerator uses `ioreg`; for the Mac App Store we should replace with a PyObjC IOKit enumerator to avoid subprocesses.
  - Capability data lives in code; moving to a small JSON source simplifies contributions and updates.
- Next steps:
  - [x] Add exporter to generate `docs/capabilities.json` from connected devices — see `export_connected_capabilities_json()`.
  - [ ] Load capabilities from JSON at runtime (fallback to built-in matrix).
  - [ ] Add a PyObjC IOKit HID enumerator (App Store–friendly) and runtime-select between it and `ioreg`.
  - [ ] Add unit tests for capability lookup and summary formatting.
  - [ ] Provide a contribution guide for adding devices to the matrix.

## Testing strategy

- Unit-test pure helpers (parsers, formatting).
- For PyObjC integration, keep logic small and guard imports to avoid test failures when frameworks aren’t present.
- Manual verification on macOS for UI.

## Rollout

- MVP via CLI `silta gui` for developer builds.
- Package as a signed/notarized .app once stable.
- Iterate on a glassy popover UI before App Store submission.
