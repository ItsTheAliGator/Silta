# macOS HID Easy-Switch Implementation# Experimental macOS HID Host Switching

The Silta client includes `silta.mac_hid`, a macOS-only helper that enablesThe Silta client includes `silta.mac_hid`, a macOS-only helper that

programmatic Easy-Switch control for Logitech MX peripherals over both Bluetoothcollects IORegistry metadata so we can identify Logitech MX peripherals and

and USB receivers. This implementation is based on proven community approachesexperiment with vendor reports. It intentionally stops short of issuing

from [SwitchMX](https://github.com/boyvanamstel/SwitchMX) and Easy-Switch commands because Logitech has not published the relevant HID

[logi-kvm](https://github.com/KonradFoit/logi-kvm).feature report definitions.

## Current Capabilities## Current capabilities

### Device Discovery- `silta.mac_hid.list_hid_devices()` runs `ioreg -lw0 -r -c IOHIDDevice -a`

- `silta.mac_hid.list_hid_devices()` - Enumerate all HID devices via IORegistry and presents results as structured `HIDDevice` objects.

- `silta.mac_hid.list_logitech_devices()` - Filter to Logitech devices (VID 0x046D)- `silta.mac_hid.list_logitech_devices()` filters to the Logitech USB vendor

- Identifies device transport (Bluetooth, USB, etc.) and product IDs ID (`0x046D`) so you can see paired MX devices and their properties.

- `silta.mac_hid.build_report_plist()` and `run_hidutil_report()` produce the

### Easy-Switch Command Sending property lists that `hidutil report` expects, paving the way for future

- **Bluetooth (BLE)**: Uses IOKit OUTPUT reports to HID++ interface (usagePage 0xFF43, usage 0x0202) experiments once a correct Easy-Switch payload is reverse engineered.

- **USB Receivers**: Uses hidapi or IOKit for Unifying/Bolt receivers

- Multi-backend fallback chain: hidutil → hidapi → IOKit## Gaps and limitations

- Tested devices: MX Master 3 Mac (0xB023), MX Master 3S (0xB034)

- Logitech’s Easy-Switch protocol (feature report IDs, payload format, and

### Protocol Implementation authentication) remains undocumented, so Silta cannot yet switch hardware

- HID++ 2.0 protocol support slots programmatically.

- Short (7-byte) and long (20-byte) report formats- `hidutil` happily transmits arbitrary reports but does **not** reveal which

- Device index inference (0xFF for BLE, slot-based for USB receivers) payload toggles Easy-Switch; discovering this requires traffic captures or

- Feature 0x1814 (Easy-Switch) command generation vendor documentation.

- MX devices span Bluetooth LE, Logi Bolt, and Unifying transports. Each uses a

## Technical Breakthroughs different descriptor, so a working payload on one device is unlikely to apply

across the range without per-model handling.

### Bluetooth Easy-Switch (November 2025)

## Suggested research path

**Key Discovery:** Bluetooth Easy-Switch requires OUTPUT reports, not FEATURE reports.

1. Capture USB/BLE traffic while Logitech Options performs an Easy-Switch

**Working Implementation:** toggle (e.g. Wireshark with the Bluetooth LE plugin or USBPcap on Windows).

```python2. Encode the discovered feature report via `build_report_plist()` and deliver

# IOKit with OUTPUT reports (kIOHIDReportTypeOutput = 1) it with `run_hidutil_report()`, targeting the matching `VendorID`/`ProductID`.

payload = [0x11, 0xFF, 0x0A, 0x1B, channel, 0x00, ...] # 20 bytes3. Harden the tooling with explicit product allowlists and guard rails to avoid

usagePage = 0xFF43 # Logitech BLE HID++ interface issuing vendor commands to unrelated hardware.

usage = 0x0202 # HID++ protocol over BLE

````Until Easy-Switch semantics are known, Silta’s software-level edge switching

remains the recommended approach.

**Why Previous Approaches Failed:**
- FEATURE reports (`kIOHIDReportTypeFeature = 2`) return `kIOReturnNotPermitted`
- IOBluetooth framework doesn't expose BLE HID devices properly
- hidapi cannot open BLE HID devices on macOS
- macOS BLE security model allows OUTPUT reports but blocks FEATURE reports

See `docs/bluetooth-easy-switch-breakthrough.md` for complete technical details.

### USB Receiver Support

**Unifying Receiver (PID 0xC52B):**
- Send interface: usagePage 0xFF00, usage 0x0001
- Listen interface: usagePage 0xFF00, usage 0x0002 (for INPUT reports)
- FEATURE reports work for command sending

**Bolt Receiver (PID 0xC548):**
- Similar interface structure to Unifying
- Compatible with same command format

## Usage

### CLI Commands

```bash
# Switch Bluetooth device to slot 2
python main.py capabilities switch --slot 2 --product-id 0xB023

# Switch USB receiver device to slot 1
python main.py capabilities switch --slot 1 --product-id 0xC52B

# List all Easy-Switch capable devices
python main.py capabilities list
````

### Programmatic Usage

```python
from silta.mac_hid import HIDDevice, easy_switch_select_host

device = HIDDevice(
    vendor_id=0x046D,
    product_id=0xB023,  # MX Master 3 Mac
    transport="Bluetooth Low Energy",
    manufacturer="Logitech",
    product="MX Master 3 Mac",
    serial_number="...",
    location_id=None
)

# Switch to slot 2
result = easy_switch_select_host(device, slot=2)
print(f"Method: {result['method']}, Bytes: {result['bytes_written']}")
```

## Supported Devices

### Tested

- ✅ MX Master 3 Mac (0xB023) - Bluetooth
- ✅ MX Master 3S (0xB034) - Bluetooth (via SwitchMX)
- ✅ Unifying Receiver (0xC52B) - USB
- ✅ Bolt Receiver (0xC548) - USB

### Should Work (Community Confirmed)

- MX Keys (various PIDs)
- MX Ergo (0x406F, 0xB023)
- MX Anywhere 3 (0xB027, 0xB02A)
- MX Vertical (0xB020)
- M720 Triathlon
- MK850 Performance

## Future Enhancements

### Bidirectional Detection (Planned)

Implement INPUT report listening for automatic Flow client triggering:

- Monitor USB receiver for Easy-Switch button presses
- Auto-connect Flow client to corresponding host
- Synchronize multiple Logitech devices
- Optional monitor input switching via DDC/CI

See `docs/easy-switch-listener-integration.md` for implementation plan.

## References

1. **SwitchMX** - https://github.com/boyvanamstel/SwitchMX
   - Bluetooth OUTPUT report approach
2. **logi-kvm** - https://github.com/KonradFoit/logi-kvm
   - INPUT report listening, multi-device sync
3. **logiSwitch** - https://github.com/nicoduj/logiSwitch
   - USB receiver reference
4. **Solaar** - https://github.com/pwr-Solaar/Solaar
   - HID++ 2.0 protocol documentation

## Limitations

- Bluetooth devices must be paired to the Mac
- USB receivers require device to be paired to the receiver
- No "Input Monitoring" permission required (despite SwitchMX requirement)
- Channel detection not yet implemented (command sending only)
