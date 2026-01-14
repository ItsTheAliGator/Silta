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
- [x] **NEW:** Device type detection (mouse/keyboard/etc.) — `silta/mac_hid.py`.
- [x] **NEW:** Internal vs external device detection — `silta/mac_hid.py`.
- [x] **NEW:** Expanded capabilities matrix (30+ Logitech devices) — `silta/capabilities.py`.
- [x] **NEW:** Unit tests for device detection — `tests/test_device_types.py`.
- [x] **NEW:** Standalone Connection Manager window with Liquid Glass (macOS 26) — `silta/connection_window.py`.

## Recent Updates (November 1, 2025)

### Completed Today

1. **Task 1 - Device Type Detection**: Added HID usage page/usage parsing to identify mice, keyboards, joysticks, gamepads, and more. Updated `HIDDevice` dataclass with `device_type` property.

2. **Task 3 - Expanded Capabilities Matrix**: Grew from 5 devices to 30+ devices including:

   - All MX Master variants (3, 3S, 2S, original)
   - MX Anywhere series (3, 3S, 2S, 2)
   - MX Keys family (standard, Mini, S, for Mac, for Business)
   - MX Mechanical keyboards
   - MX Ergo trackballs
   - Lift Vertical mice
   - K380 keyboards
   - All receiver types (Unifying, Bolt)

3. **Task 5 - Unit Tests**: Created comprehensive test suite with 15 tests covering:

   - Mouse/keyboard/joystick detection
   - Internal device identification (multiple strategies)
   - Edge cases and fallbacks
   - All tests passing ✅

4. **NEW - Standalone GUI Window**: Created `connection_window.py` with:
   - **macOS 26 Liquid Glass support** via `NSGlassEffectView`
   - Fallback to `NSVisualEffectView` for older macOS
   - Connection status monitoring (ready for integration)
   - Device listing with type icons and internal/external labels
   - Display information with specs
   - Mouse speed display
   - Sophisticated glass visual effects
   - Launched via `python main.py gui --window`

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
