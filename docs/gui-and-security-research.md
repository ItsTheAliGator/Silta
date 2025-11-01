# Silta GUI, Devices, Packaging, and Security – Research & Plan

This document outlines options to build a macOS‑only GUI that shows host/device/display info, detects capabilities, reads current display states (read‑only), stays easy to install/update, and strengthens transport security. It summarizes the main approaches with pros/cons and ends with a concrete phased plan aligned with a future Mac App Store release.

## Goals at a glance

- Show: Mac hostname, connected keyboard/mouse, internal/external displays, each display’s resolution and refresh rate, and current mouse speed.
- Enrich with icons and vendor/product details; support both internal (laptop) and external devices.
- Keep all device/display interactions read‑only. Do not send DDC/CI or other control commands.
- Experimental: show capability hints for keyboard/mouse host switching only; do not transmit vendor HID feature reports.
- Ship a simple macOS app that’s easy to install and update.
- Keep Silta’s client/server communication in Python and improve transport security.

---

## Device and display enumeration (what to use and why)

1. PyObjC + Quartz (CoreGraphics)

- What: Query displays, current mode, width/height, and refresh rate using Quartz via PyObjC.
- Pros:
  - Native, fast, reliable on macOS.
  - Exposes refresh rate from the current display mode.
- Cons:
  - Adds a dependency on PyObjC (macOS‑only, but our target is macOS‑only).

2. IORegistry (ioreg) + plistlib

- What: Shell out to `ioreg -a -rc IOHIDDevice` or IODisplay classes and parse property lists (we already do this in `silta/mac_hid.py`).
- Pros:
  - No extra third‑party module needed beyond stdlib.
  - Flexible for vendor/product/EDID information.
- Cons:
  - Interface is lower‑level; fields vary by device and OS version.

3. system_profiler (JSON)

- What: `system_profiler -json SPDisplaysDataType` (and SPUSBDataType) for user‑friendly device names.
- Pros:
  - Human‑readable, useful model naming.
- Cons:
  - Slower; best used to augment, not as the only source.

4. hidapi (`hid` Python package)

- What: Cross‑platform HID enumeration from Python.
- Pros:
  - Simple device lists with vendor/product IDs and names; complements IORegistry output.
- Cons:
  - Requires `brew install hidapi` and `pip install hid`; not strictly necessary if IORegistry covers our needs.

Recommended: Combine Quartz (refresh/resolution) + IORegistry (IDs, EDID) and optionally system_profiler for nice names. Add hidapi only if we want a friendlier enumeration fallback.

---

## Display capability and state detection (read‑only)

What to report per display:

- Name and role: internal vs external; friendly name where available.
- Resolution and scaling: point size, pixel size, backingScaleFactor.
- Refresh information: current refresh rate; maximum frames per second (for variable refresh/ProMotion panels).
- Color: current color space/profile name; wide‑gamut hint (P3).
- Topology/state: primary display, mirroring, arrangement, and rotation.

Recommended APIs (App Store‑friendly, no shelling):

- AppKit NSScreen
  - `localizedName` – friendly display name shown in System Settings (10.15+).
  - `maximumFramesPerSecond` – upper bound of variable refresh; useful on ProMotion (12+).
  - `backingScaleFactor` – pixel density (retina scaling).
  - `mirrored`/`depth`, `deviceDescription` for pixel dimensions.
- CoreGraphics (Quartz)
  - `CGGetOnlineDisplayList`, `CGDisplayIsBuiltin`, `CGDisplayPixelsWide/High`.
  - `CGDisplayCopyDisplayMode` and `CGDisplayModeGetRefreshRate` (if non‑VRR) and `CGDisplayCopyAllDisplayModes` for enumerations.
- ColorSync
  - Query current profile name to infer wide‑gamut (P3) vs sRGB.

Notes:

- There is no public AppKit/Quartz API to read external display brightness or HDR enablement that is acceptable for the App Store; do not attempt private APIs.
- Avoid `system_profiler`, `ioreg`, and `hidutil` subprocess calls for the App Store build; they may be restricted in the sandbox.
- For developer builds, these tools can augment data behind a build flag, but the UI should gracefully degrade without them.

---

## Keyboard/mouse capability hints (read‑only)

- Logitech Easy‑Switch and similar features are vendor‑specific HID feature reports and not publicly documented.
- Recommendation:
  - Detect vendor/product IDs and present capability hints only (e.g., “Easy‑Switch capable”).
  - Do not send vendor feature reports in the App Store build. Provide no UI to trigger switching.

Risk: Sending the wrong feature report can misconfigure devices. Keep this behind explicit user opt‑in and device‑specific whitelists.

---

## GUI framework options (macOS)

1. PyObjC (Cocoa) directly

- Pros:
  - Full native power and look; limitless access to macOS frameworks.
  - Enables NSVisualEffectView for the “liquid glass” look in popovers/windows.
- Cons:
  - More boilerplate; higher learning curve than rumps.

2. PySide6/PyQt6

- Pros:
  - Full‑featured widgets, great for complex windows.
- Cons:
  - Heavier runtime footprint; packaging on macOS is more involved.

3. BeeWare Toga (with Briefcase)

- Pros:
  - Native apps and a good packaging/notarization story.
- Cons:
  - Slower iteration and smaller widget ecosystem compared to Qt.

Recommended: Use PyObjC for a small native menubar app from the start so we can style the popover with NSVisualEffectView (vibrant “glass” materials). Keep the UI simple and compact.

Liquid glass look (AppKit):

- Use `NSVisualEffectView` as the background of the popover/window.
- Set `material` to an appropriate value (e.g., `.hudWindow`, `.menu`, `.popover`, `.underWindowBackground`) and `blendingMode = .behindWindow`.
- Adopt vibrancy with an NSAppearance that follows system light/dark mode.

---

## Icons and branding

- Use vendor logos where available from open icon sets (e.g., Simple Icons – CC0)
- Use device‑type icons (monitor/keyboard/mouse) from Material or similar open sets.
- Maintain a small JSON mapping from vendor/product/model → icon slug and friendly name.

Pros: Professional look with minimal effort. Cons: Some brands lack official icons; fall back to generic glyphs.

---

## Installability and updates (with a path to the Mac App Store)

Packaging options:

- Development and direct distribution:
  - py2app or Briefcase: create a signed, notarized .app that embeds Python and PyObjC.
  - Avoid shipping external helper binaries in the app bundle.
- Mac App Store path:
  - Keep to public AppKit/CoreGraphics/ColorSync APIs; no private frameworks.
  - Avoid subprocess usage of system tools (`system_profiler`, `ioreg`, `hidutil`).
  - Restrict to read‑only system queries; sandbox should be satisfied by default entitlements.
  - Briefcase’s Xcode template can help produce an App Store‑ready project; otherwise, consider a thin Swift menubar host that calls into the Python core via embedded interpreter or local loopback IPC.

Auto‑update options (for direct distribution only; the Mac App Store handles updates):

- Sparkle: best native UX; requires bridging. Not used for App Store builds.
- DIY “Check for updates”: simplest starter approach; not needed on App Store builds.

Recommended:

- Phase 1: Package with PyInstaller/py2app; provide a “Check for updates” menu item that opens the latest GitHub Release.
- Phase 2: Adopt Sparkle for background updates after we have a stable app and a notarized pipeline.

---

## Transport security improvements (keeping Python comms)

Current: HMAC token in handshake.

Options:

- TLS (ssl) wrapping the existing TCP socket
  - Pros: Mature, standard; easy to add with Python’s `ssl.SSLContext`; supports cert pinning or mTLS.
  - Cons: Requires managing certificates.
- Mutual TLS (client and server certs)
  - Pros: Strong auth; no token needed (optional to keep both).
  - Cons: Operational overhead of issuing and rotating client certs.
- Noise protocol (noiseprotocol Python)
  - Pros: Modern handshakes; small framing.
  - Cons: Library is alpha and Linux‑focused; not recommended over TLS for production on macOS.

Recommended: Enable TLS by default with a self‑signed or private CA‑issued cert bundled on the client (pinning). Keep the HMAC token for app‑level authorization. Offer an opt‑out for legacy setups during transition. Communication between machines remains a pure‑Python TCP/TLS stack.

App Store note: TLS over localhost or LAN is App Store‑safe; avoid custom or private kernel extensions.

---

## Phased plan (deliverable milestones)

Phase 1 – MVP (menu bar app)

- Use PyObjC AppKit for UI (NSStatusItem + popover with NSVisualEffectView for glass look).
- Data sources:
  - AppKit (NSScreen) + Quartz (CoreGraphics) for resolution and refresh info.
  - ColorSync for color profile name (wide‑gamut hint).
  - Optional (dev‑only) augmentation with system_profiler/IORegistry guarded by a flag.
- Icons: vendor + device‑type mapping with safe fallbacks.
- Read‑only only: No DDC control or HID feature writes.
- Add a “Check for Updates” item for direct builds (hidden in App Store build).

Phase 2 – Packaging and security

- Ship a signed & notarized .app (py2app or Briefcase). No external Homebrew dependencies.
- Add TLS option to client/server for secure transport; default on for new users.
- Maintain HMAC token; optionally add mTLS as an advanced mode.

Phase 3 – App Store readiness and capabilities

- Maintain a small JSON capability map (vendor/product → capability hints and icons).
- Remove dev‑only augmentations (system_profiler/IORegistry shells) from the App Store target; rely solely on AppKit/Quartz/ColorSync.
- Submit to App Review with sandbox enabled; iterate on any entitlement feedback.

---

## Pros and cons summary (quick table)

- Display info
  - Quartz (PyObjC): native and accurate (refresh/resolution); adds dependency.
  - system_profiler: nice names; slower.
- DDC control
  - ddcctl: practical integration; external dependency and no DDC on some links.
  - Custom IOKit DDC: powerful; high effort.
- GUI
  - rumps: fastest path for menu bar; limited for complex views.
  - PyObjC Cocoa: most native; more code.
  - PySide6/PyQt6: rich widgets; heavier packaging.
  - Toga/Briefcase: clean macOS app; slower iteration.
- Updates
  - Sparkle: best mac UX; more integration work.
  - PyUpdater: simpler Python integration; less native feel.
  - DIY check: fastest; manual download/replace.
- Security
  - TLS (ssl): standard, strong; cert mgmt required.
  - mTLS: strongest; operational overhead.
  - Noise: not production‑ready for our use.

---

## Risks and mitigations

- DDC not supported on all connections (e.g., DisplayLink): Detect and gracefully disable; offer software dimming only where it makes sense.
- Vendor HID feature reports (BT channel switching) are undocumented: Keep disabled by default; whitelist only proven devices; add clear warnings and opt‑in.
- Packaging friction and updates: Start simple; improve to Sparkle after stability.
- Dependencies (PyObjC, rumps, hidapi): Make optional where possible and fail gracefully with clear UI notes.

---

## Recommended next steps (actionable)

- Implement `silta/display.py` (Quartz info + ddcctl wrapper) and `silta/menubar.py` (rumps UI).
- Add `docs/capabilities.json` and an icon mapping file with a handful of known devices.
- Wire a `gui` CLI command to launch the menu bar app.
- Add TLS flags to client/server for secure transport; default on in the near term.
- Document Homebrew installation of ddcctl and optional hidapi.

This approach yields a useful, native‑feeling macOS UI quickly, while leaving room for a polished app bundle and stronger security as we iterate.
