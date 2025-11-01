# Easy-Switch Listener Integration Plan

## Overview

Integration of bidirectional Easy-Switch detection from [logi-kvm](https://github.com/KonradFoit/logi-kvm) to enable automatic Flow client triggering when users press Easy-Switch buttons.

## Current State (Silta)

**✅ Can Send Commands:**

- Bluetooth: OUTPUT reports via IOKit (SwitchMX approach)
- USB Receiver: Feature reports via hidapi (logiSwitch approach)

**❌ Cannot Detect Button Presses:**

- No INPUT report listening
- No automatic detection of channel switches

## What logi-kvm Provides

### 1. INPUT Report Listening

**Two HID Interfaces on Unifying Receiver:**

| Interface | Usage Page | Usage  | Purpose                     |
| --------- | ---------- | ------ | --------------------------- |
| Listen    | 0xFF00     | 0x0002 | Read INPUT reports (events) |
| Send      | 0xFF00     | 0x0001 | Write commands              |

**Reading Events:**

```python
def unifying_listen():
    h = hid.device()
    h.open_path(listen_device_path)  # path to usage 0x0002 interface
    h.set_nonblocking(0)
    data = h.read(11)  # 11-byte INPUT report
    h.close()
    return data
```

### 2. Easy-Switch Button Detection

**INPUT Report Format:**

```
[0x11, slot_id, 0x08, 0x20, 0x00, key_code, key_state]
  ^^     ^^                        ^^        ^^
header  slot                    button ID   pressed/released
```

**Key Codes:**

- Button 1: `0xD1`
- Button 2: `0xD2`
- Button 3: `0xD3`

**Decoding Logic:**

```python
def decode_target_channel_number(input_bytes, switch_detect_message, easy_switch_keys):
    # Compare header, slot, constants
    if input_bytes[:4] == switch_detect_message[:4]:
        # Check key state (byte 6 = 0x01 for pressed)
        if input_bytes[6] == 0x01:
            # Find which button was pressed
            for i, key in enumerate(easy_switch_keys):
                if key == input_bytes[5]:
                    return i  # Return channel number (0, 1, or 2)
    return -1
```

### 3. Device Configurations

**MX Master 3:**

```python
switch_detect_message = [0x11, 0x01, 0x08, 0x20, 0x00, 0xFF, 0x01]
easy_switch_keys = [0xD1, 0xD2, 0xD3]
switch_message = [0x10, 0x01, 0x09, 0x1E, 0xFF, 0x00, 0x00]  # byte 4 = channel
max_channels = 3
```

**MX Keys:**

```python
switch_detect_message = [0x11, 0x01, 0x08, 0x20, 0x00, 0xFF, 0x01]
easy_switch_keys = [0xD1, 0xD2, 0xD3]
switch_message = [0x10, 0x01, 0x09, 0x1E, 0xFF, 0x00, 0x00]
max_channels = 3
```

**MX Ergo:**

```python
switch_detect_message = []  # No button press events
easy_switch_keys = []
switch_message = [0x10, 0x02, 0x15, 0x1B, 0xFF, 0x00, 0x00]
max_channels = 2
```

### 4. Multi-Device Synchronization

**Core Logic:**

```python
def switch_channel(channel_number, detection_slot, all_devices):
    # Switch all devices EXCEPT the one that triggered the event
    for device in all_devices:
        if device.slot_id != detection_slot:
            device.switch_channel(channel_number)
```

## Integration with Silta

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Silta Flow Client                        │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │          Easy-Switch Listener Thread                   │ │
│  │  (monitors USB receiver for button presses)            │ │
│  └─────────────────┬──────────────────────────────────────┘ │
│                    │ detects channel switch                 │
│                    ▼                                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │       Channel Switch Handler                          │ │
│  │  - Maps channel → remote host                         │ │
│  │  - Triggers Flow client connection                    │ │
│  │  - Switches other devices (keyboard, etc.)            │ │
│  │  - Optional: switch monitor input                     │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### New Module: `silta/easy_switch_listener.py`

```python
"""Easy-Switch button press detection for automatic Flow client triggering."""

import hid
import threading
import time
from typing import Callable, Dict, Optional
from .utils import LOG

class EasySwitchListener:
    """Monitors Unifying receiver for Easy-Switch button presses."""

    def __init__(self,
                 channel_to_host: Dict[int, str],
                 on_channel_switch: Callable[[int, str], None]):
        """
        Args:
            channel_to_host: Map of channel numbers to remote host addresses
            on_channel_switch: Callback(channel, host) when switch detected
        """
        self.channel_to_host = channel_to_host
        self.on_channel_switch = on_channel_switch
        self.running = False
        self.thread = None
        self.listen_path = None

    def _discover_receiver(self):
        """Find Unifying receiver listen interface."""
        for dev in hid.enumerate(0x046D, 0xC52B):  # Logitech Unifying
            if dev['usage_page'] == 0xFF00 and dev['usage'] == 0x0002:
                self.listen_path = dev['path']
                LOG.info(f"Found Unifying receiver listen interface")
                return True
        return False

    def _read_input(self) -> Optional[list]:
        """Read 11-byte INPUT report from receiver."""
        try:
            h = hid.device()
            h.open_path(self.listen_path)
            h.set_nonblocking(1)  # Non-blocking for graceful shutdown
            data = h.read(11, timeout_ms=100)
            h.close()
            return list(data) if data else None
        except Exception as e:
            LOG.debug(f"Input read error: {e}")
            return None

    def _decode_channel(self, input_bytes: list) -> int:
        """Decode target channel from INPUT report.

        Format: [0x11, slot, 0x08, 0x20, 0x00, key_code, 0x01]
        Key codes: 0xD1 (ch0), 0xD2 (ch1), 0xD3 (ch2)
        """
        if not input_bytes or len(input_bytes) < 7:
            return -1

        # Check header and constants
        if (input_bytes[0] == 0x11 and
            input_bytes[2] == 0x08 and
            input_bytes[3] == 0x20 and
            input_bytes[4] == 0x00 and
            input_bytes[6] == 0x01):  # Key pressed

            key_code = input_bytes[5]
            # Map key codes to channels
            if key_code == 0xD1:
                return 0
            elif key_code == 0xD2:
                return 1
            elif key_code == 0xD3:
                return 2
        return -1

    def _listen_loop(self):
        """Main listening loop."""
        LOG.info("Easy-Switch listener started")
        while self.running:
            data = self._read_input()
            if data:
                channel = self._decode_channel(data)
                if channel >= 0 and channel in self.channel_to_host:
                    host = self.channel_to_host[channel]
                    LOG.info(f"Easy-Switch detected: channel {channel} → {host}")
                    self.on_channel_switch(channel, host)
            time.sleep(0.05)  # 50ms polling
        LOG.info("Easy-Switch listener stopped")

    def start(self) -> bool:
        """Start listening thread."""
        if not self._discover_receiver():
            LOG.warning("No Unifying receiver found for Easy-Switch listening")
            return False

        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        """Stop listening thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
```

### Integration into FlowClient

**Updated `silta/client.py`:**

```python
class FlowClient:
    def __init__(self, ...):
        # ... existing code ...
        self.easy_switch_listener = None

    def enable_easy_switch_auto_connect(self, channel_to_host: Dict[int, str]):
        """Enable automatic connection when Easy-Switch buttons pressed.

        Args:
            channel_to_host: {0: "192.168.1.10", 1: "192.168.1.20", 2: "192.168.1.30"}
        """
        from .easy_switch_listener import EasySwitchListener

        def on_channel_switch(channel: int, host: str):
            # Disconnect current connection
            if self.is_connected():
                self.disconnect()

            # Connect to new host
            LOG.info(f"Auto-connecting to {host} (channel {channel})")
            self.connect(host, self.port)

        self.easy_switch_listener = EasySwitchListener(
            channel_to_host=channel_to_host,
            on_channel_switch=on_channel_switch
        )

        if self.easy_switch_listener.start():
            LOG.info("Easy-Switch auto-connect enabled")
        else:
            LOG.warning("Failed to enable Easy-Switch auto-connect")
```

### CLI Integration

**Updated `silta/cli.py`:**

```python
def build_parser():
    # ... existing code ...

    client_parser.add_argument(
        '--easy-switch-auto',
        action='store_true',
        help='Enable automatic connection based on Easy-Switch button presses'
    )

    client_parser.add_argument(
        '--easy-switch-profile',
        type=argparse.FileType('r'),
        help='JSON profile mapping channels to hosts: {"0": "host1", "1": "host2", "2": "host3"}'
    )

def main():
    # ... existing code ...

    if args.command == 'client':
        client = FlowClient(...)

        if args.easy_switch_auto and args.easy_switch_profile:
            import json
            profile = json.load(args.easy_switch_profile)
            channel_to_host = {int(k): v for k, v in profile.items()}
            client.enable_easy_switch_auto_connect(channel_to_host)

        client.run()
```

### Configuration Example

**`easy-switch-profile.json`:**

```json
{
	"0": "192.168.1.10",
	"1": "192.168.1.20",
	"2": "192.168.1.30",
	"port": 59873,
	"auth_token": "secret"
}
```

### Usage Example

```bash
# Start client with Easy-Switch auto-connect
python main.py client \
  --server 192.168.1.10 \
  --easy-switch-auto \
  --easy-switch-profile easy-switch-profile.json
```

Now when user presses Easy-Switch button 2:

1. Listener detects button press (key code 0xD2)
2. Decodes as channel 1
3. Maps to host "192.168.1.20"
4. Automatically connects Flow client to that host
5. User's mouse/keyboard now control the other computer

## Advanced Features

### 1. Multi-Device Synchronization

Keep keyboard and mouse in sync:

```python
def on_channel_switch(channel: int, host: str):
    # Switch Flow client
    client.connect(host, port)

    # Switch other Logitech devices to same channel
    from .capabilities import switch_all_devices_to_channel
    switch_all_devices_to_channel(channel)
```

### 2. Monitor Input Switching

Automatically switch monitor inputs (requires DDC/CI):

```python
def on_channel_switch(channel: int, host: str):
    # ... connect Flow client ...

    # Switch monitor input
    from .display_info import switch_monitor_input
    input_map = {0: "HDMI1", 1: "HDMI2", 2: "DisplayPort"}
    switch_monitor_input(input_map[channel])
```

### 3. Bluetooth Device Support

For Bluetooth devices, detect via polling current channel:

```python
class BluetoothEasySwitchPoller:
    """Detect channel switches by polling device state."""

    def poll_current_channel(self, device: HIDDevice) -> int:
        """Read current channel from device (if supported)."""
        # Some devices report current channel via HID++ 0x1814 feature
        # Implementation TBD based on device capabilities
        pass
```

## Testing Plan

### Phase 1: USB Receiver Listening

- [ ] Implement `EasySwitchListener` class
- [ ] Test INPUT report reading from Unifying receiver
- [ ] Verify button press detection for all 3 buttons
- [ ] Test with MX Master 3, MX Keys, MX Ergo

### Phase 2: FlowClient Integration

- [ ] Add auto-connect callback to FlowClient
- [ ] Test automatic connection triggering
- [ ] Verify graceful disconnection before reconnecting
- [ ] Test with edge-triggered flow (ensure no conflicts)

### Phase 3: Multi-Device Sync

- [ ] Implement device synchronization (switch all devices)
- [ ] Test with multiple Logitech devices
- [ ] Verify skip logic (don't switch device that triggered event)

### Phase 4: Bluetooth Support

- [ ] Research Bluetooth channel detection methods
- [ ] Implement polling-based detection if feasible
- [ ] Test with BLE-connected devices

## Benefits for Silta

1. **Zero-Configuration KVM**: Users just press Easy-Switch, Silta handles the rest
2. **Hardware Integration**: Leverages existing Logitech Easy-Switch buttons
3. **Seamless Experience**: No need to remember keyboard shortcuts
4. **Multi-Device Sync**: All Logitech devices switch together
5. **Monitor Integration**: Optional automatic monitor input switching

## Related Work

- **logi-kvm**: https://github.com/KonradFoit/logi-kvm

  - Windows-focused, monitor DDC/CI integration
  - Proven INPUT report listening approach
  - Multi-device synchronization logic

- **SwitchMX**: https://github.com/boyvanamstel/SwitchMX

  - macOS Bluetooth OUTPUT reports (command sending)
  - Does NOT listen for button presses

- **logiSwitch**: https://github.com/nicoduj/logiSwitch
  - USB receiver command sending
  - No INPUT report listening

Silta will be the **first** macOS implementation combining:

- ✅ Bluetooth command sending (from SwitchMX)
- ✅ USB receiver command sending (from logiSwitch)
- ✅ INPUT report listening (from logi-kvm)
- ✅ Flow client integration (unique to Silta)

## Timeline

- **Week 1**: Implement `EasySwitchListener` and test INPUT reading
- **Week 2**: Integrate with FlowClient, test auto-connect
- **Week 3**: Add multi-device sync, monitor switching
- **Week 4**: Polish, documentation, user testing

## Success Criteria

- [ ] Easy-Switch button presses detected reliably (<100ms latency)
- [ ] Flow client connects to correct host automatically
- [ ] Multiple Logitech devices stay synchronized
- [ ] Works seamlessly with existing edge-triggered flow
- [ ] Documented configuration examples
- [ ] Tested on macOS with Unifying receiver and Bluetooth
