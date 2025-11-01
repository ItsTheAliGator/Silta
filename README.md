# Silta

Silta is a Python tool for sharing mouse and keyboard input between macOS
machines. It mirrors a Logitech Flow style workflow with software-managed edge
activation, optional multi-host profiles, and macOS-native event capture.

## Features

- **Client/Server architecture** – `FlowClient` streams local events to a
  remote `FlowServer` over TCP with a minimal JSON protocol.
- **Edge-triggered switching** – move the cursor to a configured screen edge to
  start or stop forwarding input; optional edge profiles map edges to different
  remote hosts.
- **macOS Quartz integrations** – native event taps and CGEvent injection keep
  latency low while respecting Accessibility permissions.
- **HID research helpers** – experimental `mac_hid` utilities enumerate Logitech
  MX devices and prepare `hidutil` payloads for future host-switch automation.

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

Install the development extras and run:

```bash
pytest
```

## Module Guide

| Component                   | Location                | Purpose                                                                                   |
| --------------------------- | ----------------------- | ----------------------------------------------------------------------------------------- |
| `build_parser()` / `main()` | `silta/cli.py`          | Define CLI commands, parse arguments, and launch client or server modes.                  |
| `FlowClient`                | `silta/client.py`       | Manages macOS event taps, edge detection, hotkeys, and TCP communication with the server. |
| `FlowServer`                | `silta/server.py`       | Receives JSON events and injects them via Quartz CGEvents (macOS) or `pynput` fallbacks.  |
| `LocalCursorManager`        | `silta/local_cursor.py` | Hides, warps, or freezes the local cursor while remote control is active.                 |
| `CursorAdapter`             | `silta/cursor.py`       | Provides unified cursor operations across Quartz, PyAutoGUI, and `pynput` backends.       |
| Protocol helpers            | `silta/protocol.py`     | Build/validate handshake messages with optional HMAC authentication.                      |
| Hotkey utilities            | `silta/keys.py`         | Normalize key names and map edges to their counterparts.                                  |
| `mac_hid` helpers           | `silta/mac_hid.py`      | Experimental IORegistry parsing and `hidutil` report builders for Logitech MX research.   |

Additional background on HID host switching lives in
`docs/mac-host-switching.md`.

## Accessibility & Permissions

On macOS the client relies on a Quartz event tap to suppress local input. When
you run the client for the first time, macOS will prompt for Accessibility
access. Approve the request in **System Settings → Privacy & Security →
Accessibility** for your terminal or Python interpreter.

## License

This project is distributed under the MIT license. See `LICENSE` (if present)
or the repository metadata for details.
