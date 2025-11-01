# Experimental macOS HID Host Switching

The Silta client includes `silta.mac_hid`, a macOS-only helper that
collects IORegistry metadata so we can identify Logitech MX peripherals and
experiment with vendor reports. It intentionally stops short of issuing
Easy-Switch commands because Logitech has not published the relevant HID
feature report definitions.

## Current capabilities

- `silta.mac_hid.list_hid_devices()` runs `ioreg -lw0 -r -c IOHIDDevice -a`
  and presents results as structured `HIDDevice` objects.
- `silta.mac_hid.list_logitech_devices()` filters to the Logitech USB vendor
  ID (`0x046D`) so you can see paired MX devices and their properties.
- `silta.mac_hid.build_report_plist()` and `run_hidutil_report()` produce the
  property lists that `hidutil report` expects, paving the way for future
  experiments once a correct Easy-Switch payload is reverse engineered.

## Gaps and limitations

- Logitech’s Easy-Switch protocol (feature report IDs, payload format, and
  authentication) remains undocumented, so Silta cannot yet switch hardware
  slots programmatically.
- `hidutil` happily transmits arbitrary reports but does **not** reveal which
  payload toggles Easy-Switch; discovering this requires traffic captures or
  vendor documentation.
- MX devices span Bluetooth LE, Logi Bolt, and Unifying transports. Each uses a
  different descriptor, so a working payload on one device is unlikely to apply
  across the range without per-model handling.

## Suggested research path

1. Capture USB/BLE traffic while Logitech Options performs an Easy-Switch
   toggle (e.g. Wireshark with the Bluetooth LE plugin or USBPcap on Windows).
2. Encode the discovered feature report via `build_report_plist()` and deliver
   it with `run_hidutil_report()`, targeting the matching `VendorID`/`ProductID`.
3. Harden the tooling with explicit product allowlists and guard rails to avoid
   issuing vendor commands to unrelated hardware.

Until Easy-Switch semantics are known, Silta’s software-level edge switching
remains the recommended approach.
