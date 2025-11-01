# Bluetooth Easy-Switch Breakthrough

## Summary

Successfully implemented Bluetooth Easy-Switch for Logitech mice on macOS using OUTPUT reports via IOKit. This was previously thought to be impossible due to macOS BLE security restrictions.

## The Discovery

User provided [SwitchMX repository](https://github.com/boyvanamstel/SwitchMX), a Swift macOS app that successfully switches channels on MX Master 3S over Bluetooth.

## Key Technical Findings

### What Works

1. **Report Type**: `kIOHIDReportTypeOutput` (value: 1)

   - NOT `kIOHIDReportTypeFeature` (value: 2)
   - This is the critical difference!

2. **HID Interface**: Must target the Logitech vendor-specific BLE interface

   - `usagePage`: `0xFF43` (65347 decimal)
   - `usage`: `0x0202` (514 decimal)

3. **Payload Format**: 20-byte OUTPUT report

   ```
   [0x11, 0xFF, 0x0A, 0x1B, channel, 0x00, 0x00, ... (pad to 20 bytes)]
   ```

   - Byte 0: `0x11` - Report ID (long HID++ report)
   - Byte 1: `0xFF` - Device index (BLE devices)
   - Bytes 2-3: `0x0A, 0x1B` - Feature/function identifiers
   - Byte 4: Channel (0, 1, or 2 for slots 1, 2, 3)
   - Remaining: Zero padding

4. **IOKit Matching**: Include usage page/usage in device matching
   ```c
   matchingDict = {
       kIOHIDVendorIDKey: 0x046D,
       kIOHIDProductIDKey: 0xB023,
       kIOHIDDeviceUsagePageKey: 0xFF43,
       kIOHIDDeviceUsageKey: 0x0202
   }
   ```

### What Doesn't Work

All of these approaches were tried and failed:

1. **FEATURE reports** (`kIOHIDReportTypeFeature`)

   - Returns: `kIOReturnNotPermitted` (-536870160)
   - This was the original attempt

2. **IOBluetooth framework** L2CAP channels
   - PSM 0x11 (control) and 0x13 (interrupt) channels inaccessible
   - BLE devices show as "not connected" even when paired and active
3. **IOBluetoothHIDDevice** class

   - Not accessible for user-space BLE HID devices
   - Works for Classic Bluetooth, not BLE

4. **hidapi** (`hid.write()`)
   - Cannot open BLE HID devices
   - Error: "unable to open device"

## Implementation Path

### Swift (SwitchMX approach)

```swift
let outputData: [UInt8] = [0x11, 0xFF, 0x0A, 0x1B, channel,
                           0x00, 0x00, 0x00, 0x00, 0x00,
                           0x00, 0x00, 0x00, 0x00, 0x00,
                           0x00, 0x00, 0x00, 0x00, 0x00]

let manager = IOHIDManagerCreate(kCFAllocatorDefault, IOOptionBits(kIOHIDOptionsTypeNone))
IOHIDManagerSetDeviceMatching(manager, matchingDict as CFDictionary)
IOHIDManagerOpen(manager, IOOptionBits(kIOHIDOptionsTypeNone))

for device in devices {
    IOHIDDeviceOpen(device, IOOptionBits(kIOHIDOptionsTypeNone))
    IOHIDDeviceSetReport(device,
                       kIOHIDReportTypeOutput,
                       CFIndex(outputData[0]),
                       buffer.baseAddress!,
                       buffer.count)
    IOHIDDeviceClose(device, IOOptionBits(kIOHIDOptionsTypeNone))
}
```

### Python (Silta implementation)

```python
def _easy_switch_via_iokit_ble(device: HIDDevice, slot: int):
    # Build payload
    channel = (slot - 1) & 0xFF
    payload = [0x11, 0xFF, 0x0A, 0x1B, channel]
    while len(payload) < 20:
        payload.append(0x00)
    payload_bytes = bytes(payload)

    # Set up IOKit matching with usage page/usage
    matching = IOServiceMatching(b"IOHIDDevice")
    _set_int_key(matching, b"VendorID", device.vendor_id)
    _set_int_key(matching, b"ProductID", device.product_id)
    _set_int_key(matching, b"DeviceUsagePage", 0xFF43)
    _set_int_key(matching, b"DeviceUsage", 0x0202)

    # Send OUTPUT report
    kr = IOHIDDeviceSetReport(device_ref,
                             kIOHIDReportTypeOutput,  # KEY DIFFERENCE!
                             report_id,
                             buffer,
                             len(payload_bytes))
```

## Testing Results

### Test Device

- **Model**: MX Master 3 Mac
- **Product ID**: 0xB023
- **Connection**: Bluetooth Low Energy (BLE)
- **Transport**: "Bluetooth Low Energy"

### Swift Test

```bash
./test_switchmx.swift
```

Output:

```
IOHIDDeviceSetReport result: 0 (0x0)
✅ SUCCESS! Easy-Switch command sent successfully!
```

### Python Test

```bash
python main.py capabilities switch --slot 2 --product-id 0xB023
```

Output:

```
Switched MX Master 3 Mac to slot 2
```

### Slot Testing

- **Slot 1**: ✅ Works
- **Slot 2**: ✅ Works
- **Slot 3**: ⚠️ "No Easy-Switch capable devices detected" (device not paired to slot 3)

## Why Previous Approaches Failed

### FEATURE Reports

The original implementation (and most community tools) used FEATURE reports because:

1. HID++ 2.0 specification describes features as FEATURE reports
2. USB receivers accept FEATURE reports successfully
3. It's the "correct" HID++ protocol approach

However, macOS BLE HID driver appears to:

- Allow OUTPUT reports to pass through to user space
- Block FEATURE reports with `kIOReturnNotPermitted`

This security model makes sense: OUTPUT reports are for sending data (keyboard, mouse output), while FEATURE reports are for device configuration.

### IOBluetooth Framework

The framework is designed for Classic Bluetooth (not BLE). While it can discover and pair BLE devices:

- It doesn't expose "connected" state properly for BLE HID
- L2CAP channels (`getL2CAPChannels`) return empty or are inaccessible
- `IOBluetoothHIDDevice` class doesn't work with BLE HID devices

### hidapi

The `hid` Python package (and underlying hidapi library):

- Can enumerate BLE HID devices successfully
- Shows all 4 interfaces including the HID++ interface (0xFF43/0x0202)
- Cannot open any of them ("unable to open device")

This is because hidapi on macOS uses IOKit's IOHIDManager, which requires opening the device - but the BLE HID driver maintains exclusive access for FEATURE operations.

## References

1. **SwitchMX** (working implementation)

   - https://github.com/boyvanamstel/SwitchMX
   - Swift macOS app for MX Master 3S
   - Uses IOKit OUTPUT reports
   - Requires "Input Monitoring" permission (which we DON'T need?)

2. **logiSwitch** (USB receiver approach)

   - https://github.com/nicoduj/logiSwitch
   - Explicitly states: "Connecting via bluetooth did not work through my tests"
   - Uses USB Unifying/Bolt receivers successfully

3. **input-switcher** (USB receiver approach)

   - https://github.com/marcelhoffs/input-switcher
   - Another USB-only implementation

4. **Solaar** (Linux, USB receiver)
   - https://github.com/pwr-Solaar/Solaar
   - Reference for HID++ 2.0 protocol details

## Lessons Learned

1. **Community repos can be misleading** - logiSwitch README says "Bluetooth didn't work", but the _approach_ was wrong, not the connection type.

2. **Report type matters more than protocol correctness** - Using "incorrect" OUTPUT reports instead of "correct" FEATURE reports is what enables BLE access.

3. **Interface filtering is critical** - Must specify `usagePage` and `usage` in IOKit matching to target the right interface.

4. **Test with native code first** - Swift test confirmed the approach before debugging Python bindings.

5. **macOS BLE security model** - Not a blanket "no user-space access", but rather "no FEATURE report access". OUTPUT reports work fine.

## Future Work

1. **Verify Input Monitoring permission** - SwitchMX requires it, but our Python implementation seems to work without it. Investigate why.

2. **Test with more devices**:

   - MX Master 3S (PID 0xB034) - confirmed in SwitchMX
   - MX Anywhere 3 (PID 0xB027, 0xB02A)
   - MX Keys (various PIDs)

3. **Explore other HID++ features** via OUTPUT reports:

   - DPI switching
   - Button remapping
   - Pointer speed

4. **Document C/D byte variations** (bytes 2-3 of payload):

   - Current: `0x0A, 0x1B` works for MX Master 3/3S
   - Alternatives: `0x09, 0x1B`, `0x0C, 0x1E` mentioned in community logs
   - May be device-specific

5. **Bidirectional Easy-Switch Detection** ⭐ NEW!
   - Implement INPUT report listening (from [logi-kvm](https://github.com/KonradFoit/logi-kvm))
   - Detect when user presses Easy-Switch buttons
   - Auto-trigger Flow client connection to corresponding host
   - See: `docs/easy-switch-listener-integration.md`

## Acknowledgments

- **SwitchMX** by Boy van Amstel - The working implementation that made Bluetooth switching possible
- **logi-kvm** by Konrad Foit - INPUT report listening for bidirectional Easy-Switch detection
- **logiSwitch** by nicoduj - USB receiver reference implementation
- **input-switcher** by marcelhoffs - Additional USB receiver insights
- **Solaar** project - HID++ 2.0 protocol documentation
