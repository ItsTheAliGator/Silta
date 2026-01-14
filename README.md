# Silta

Silta is a Python tool for sharing mouse and keyboard input between macOS
machines. It mirrors a Logitech Flow style workflow with software-managed edge
activation, optional multi-host profiles, and macOS-native event capture.

## Features

remote `FlowServer` over TCP with a minimal JSON protocol.
start or stop forwarding input; optional edge profiles map edges to different
remote hosts.
latency low while respecting Accessibility permissions.
Logitech Easy-Switch support.
receivers (uses proven SwitchMX approach for BLE devices).

- **Modern GUI** – macOS menubar and standalone window with device monitoring,
  connection management, and Liquid Glass visual effects (macOS 26+).
- **Comprehensive device detection** – automatic identification of device types
  (mouse, keyboard, etc.) and internal vs external devices.
- **Expanded device support** – 30+ Logitech devices with Easy-Switch capabilities.

## Installation

Silta targets Python 3.9 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e '.[dev]'
```

The client requires `pyautogui` and `pynput`, which are declared in
`pyproject.toml`. macOS users must grant Accessibility permissions to the
terminal running Silta so the event tap can suppress local input.

## Usage

### Server

Run the server on the machine that should receive input:

```bash
python3 main.py server --host 0.0.0.0 --port 59873 --auth-token YOUR_TOKEN
```

### Client

Basic client invocation:

```bash
python3 main.py client --server SERVER_HOST --port 59873 --auth-token YOUR_TOKEN
```

Edge-triggered multi-host switching can be described with a JSON profile:

```json
{
	"left": { "host": "192.168.0.10", "port": 59873 },
	"right": { "host": "192.168.0.20", "port": 59873, "auth_token": "alt" },
	"default": { "host": "192.168.0.10" }
}
```

Launch the client with the profile:

```bash
python3 main.py client \
  --server 192.168.0.10 \
  --edge auto \
  --edge-profile /path/to/profile.json \
  --auth-token YOUR_TOKEN
```

Self-test utilities validate protocol helpers without starting the network
stack:

```bash
python3 main.py --self-test
```

### Testing

**Menubar Mode** (default):

The menubar app displays:

````bash
- Connected HID devices grouped by type (🖱️ Mice, ⌨️ Keyboards, etc.)
- Device type detection and internal/external indicators
- Capability hints for each device (Easy-Switch, Bluetooth, etc.)
- Export device capabilities to JSON
- Interactive Easy-Switch testing controls
Install optional GUI dependencies and launch the menubar:
**Standalone Window Mode** (NEW - macOS 26+):
```bash
Launch the modern connection manager window with Liquid Glass effects:

```bash
python3 main.py gui --window
````

Features:

- **Liquid Glass UI** – Uses macOS 26 `NSGlassEffectView` for sophisticated translucent effects
- **Connection monitoring** – Real-time status of Flow client connections
- **Device overview** – All connected devices with type icons and capabilities
- **Display information** – Complete display specs at a glance
- **Automatic fallback** – Uses `NSVisualEffectView` on macOS 15 and earlier

Note: Both GUIs are primarily read-only for device information. Easy-Switch controls are available in menubar mode.
pip install -e '.[gui]'
python3 main.py gui

````

The MVP displays:

- Hostname
- Displays (internal/external, resolution, scale, refresh rate or VRR max)
- Connected HID devices with capability hints (Easy-Switch, DPI settings, etc.)
- Current mouse speed (read-only)
- Export device capabilities to JSON

Note: The GUI is read-only. It does not attempt DDC control or send vendor HID feature reports.

### Easy-Switch CLI (Bluetooth & USB Receivers)

Switch Logitech Easy-Switch devices between host slots:

```bash
# Works with both Bluetooth and USB receivers!
python3 main.py capabilities switch --slot 2 --product-id 0xB023
````

**Proven macOS Support:**

- ✅ **Bluetooth works!** - Uses OUTPUT reports via IOKit (SwitchMX approach)
  - Tested with MX Master 3 (PID 0xB023), MX Master 3S (PID 0xB034)
  - Requires Bluetooth device to be paired (no Input Monitoring permission needed)
- ✅ **USB receivers work** - Unifying (PID 0xC52B), Bolt (PID 0xC548)

**How it works:**
This implementation is based on [SwitchMX](https://github.com/boyvanamstel/SwitchMX),
which discovered that Bluetooth Easy-Switch requires OUTPUT reports (not FEATURE reports)
sent to the HID++ interface (usagePage 0xFF43, usage 0x0202) with the specific payload format:
`[0x11, 0xFF, 0x0A, 0x1B, channel, ...]`

Previous attempts using FEATURE reports, L2CAP channels, or IOBluetooth framework all failed.
The key insight was using `kIOHIDReportTypeOutput` instead of `kIOHIDReportTypeFeature`.

## Module Guide

| Component                   | Location                | Purpose                                                                                    |
| --------------------------- | ----------------------- | ------------------------------------------------------------------------------------------ |
| `build_parser()` / `main()` | `silta/cli.py`          | Define CLI commands, parse arguments, and launch client or server modes.                   |
| `FlowClient`                | `silta/client.py`       | Manages macOS event taps, edge detection, hotkeys, and TCP communication with the server.  |
| `FlowServer`                | `silta/server.py`       | Receives JSON events and injects them via Quartz CGEvents (macOS) or `pynput` fallbacks.   |
| `LocalCursorManager`        | `silta/local_cursor.py` | Hides, warps, or freezes the local cursor while remote control is active.                  |
| `CursorAdapter`             | `silta/cursor.py`       | Provides unified cursor operations across Quartz, PyAutoGUI, and `pynput` backends.        |
| Protocol helpers            | `silta/protocol.py`     | Build/validate handshake messages with optional HMAC authentication.                       |
| Hotkey utilities            | `silta/keys.py`         | Normalize key names and map edges to their counterparts.                                   |
| `mac_hid` helpers           | `silta/mac_hid.py`      | HID device enumeration, Easy-Switch control (Bluetooth/USB), multi-backend fallback chain. |
| `capabilities` system       | `silta/capabilities.py` | Device capability detection and Easy-Switch controller for supported devices.              |
| Display information         | `silta/display_info.py` | macOS display enumeration and property detection.                                          |

Additional background on HID host switching lives in
`docs/mac-host-switching.md`.

For a broader plan covering the macOS GUI, device/display capabilities, packaging, and transport security, see `docs/gui-and-security-research.md`.

## Accessibility & Permissions

On macOS the client relies on a Quartz event tap to suppress local input. When
you run the client for the first time, macOS will prompt for Accessibility
access. Approve the request in **System Settings → Privacy & Security →
Accessibility** for your terminal or Python interpreter.

## License

This project is distributed under the MIT license. See `LICENSE` (if present)
or the repository metadata for details.
