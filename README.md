# Silta

Silta is a Python tool for sharing mouse and keyboard input between macOS
machines. It mirrors a Logitech Flow style workflow with software-managed edge
activation, optional multi-host profiles, and macOS-native event capture.

## Features

- **Networked Input Sharing** – Remote `FlowServer` over TCP with a minimal JSON protocol.
- **Edge Activation** – Start or stop forwarding input; optional edge profiles map edges to different remote hosts.
- **Native macOS Events** – Uses Quartz event taps for low latency while respecting Accessibility permissions.
- **Easy-Switch Support** – Control Logitech devices (Bluetooth & Unifying/Bolt receivers) to switch hosts automatically.

### GUI Features

- **Modern GUI** – macOS menubar and standalone window with device monitoring and connection management.
- **Liquid Glass UI** – Uses `NSVisualEffectView` for a native macOS look (dark mode compatible).
- **Comprehensive Device Detection** – Automatic identification of device types (mouse, keyboard) and connection methods.
- **Interactive Controls** – Toggle Easy-Switch slots directly from the interface.

## Installation

Silta targets Python 3.9 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
# Install core dependencies
pip install -e '.[dev]'
# Install GUI dependencies (optional)
pip install -e '.[gui]'
```

The client requires `pyautogui` and `pynput`. macOS users must grant Accessibility permissions to the terminal running Silta so the event tap can suppress local input.

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

### GUI Mode

Launch the standalone connection manager window:

```bash
python3 main.py gui --window
```

Or launch the menubar app:

```bash
python3 main.py gui
```

### Easy-Switch CLI

Switch Logitech Easy-Switch devices between host slots (supports Bluetooth & USB receivers):

```bash
python3 main.py capabilities switch --slot 2 --product-id 0xB023
```

## Module Guide

| Package/Module          | Location                     | Purpose                                                                 |
| ----------------------- | ---------------------------- | ----------------------------------------------------------------------- |
| `silta.cli`             | `silta/cli.py`               | CLI entry point, argument parsing, and mode selection.                  |
| `silta.client`          | `silta/client/`              | Client logic, `FlowClient`, and macOS event tap handling.               |
| `silta.server`          | `silta/server/`              | Server logic, `FlowServer`, and event injection.                        |
| `silta.hid`             | `silta/hid/`                 | HID device enumeration, data models, and backends (IOKit, hidapi).      |
| `silta.gui`             | `silta/gui/`                 | GUI implementation (Window, Tabs, Views) using PyObjC.                  |
| `silta.utils`           | `silta/utils/`               | Shared utilities for logging, errors, and dependency management.        |
| `silta.capabilities`    | `silta/capabilities.py`      | high-level device capability registry (hints for UI).                   |

## License

This project is distributed under the MIT license.
