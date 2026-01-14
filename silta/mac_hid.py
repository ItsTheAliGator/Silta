"""macOS HID helpers for Logitech Easy-Switch control.

This module provides programmatic Easy-Switch control for Logitech MX devices
via both Bluetooth (BLE) and USB receivers (Unifying/Bolt). Implementation is
based on proven community approaches from SwitchMX and logi-kvm.

Key Features:
- Device enumeration via IORegistry
- Easy-Switch command sending (Bluetooth and USB)
- Multi-backend fallback chain (hidutil → hidapi → IOKit)
- HID++ 2.0 protocol support

Technical Approach:
- Bluetooth: OUTPUT reports via IOKit (usagePage 0xFF43, usage 0x0202)
- USB Receivers: FEATURE reports via hidapi or IOKit

See docs/bluetooth-easy-switch-breakthrough.md for technical details.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
import ctypes
from ctypes import util
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from .utils import LOG


@dataclass
class HIDDevice:
    vendor_id: int
    product_id: int
    transport: Optional[str]
    manufacturer: Optional[str]
    product: Optional[str]
    serial_number: Optional[str]
    location_id: Optional[int]
    usage_page: Optional[int] = None
    usage: Optional[int] = None
    built: Optional[bool] = None

    def matching_dict(self) -> dict:
        """Return an ``hidutil`` matching dictionary for the device."""

        match = {"VendorID": self.vendor_id, "ProductID": self.product_id}
        if self.serial_number:
            match["SerialNumber"] = self.serial_number
        return match

    @property
    def device_type(self) -> str:
        """
        Determine device type from HID usage page/usage, with overrides for known devices.
        
        Many composite HID devices (especially Logitech) expose multiple interfaces,
        and we may only see one HID usage. Use product name and VID/PID to override
        classification for well-known devices.
        
        Standard HID Usage Tables (USB HID 1.11):
        - Usage Page 1 (Generic Desktop):
            - Usage 2 = Mouse
            - Usage 6 = Keyboard  
            - Usage 4 = Joystick
            - Usage 5 = Game Pad
            - Usage 8 = Multi-axis Controller
        - Usage Page 12 (Consumer): Remote controls
        """
        # Check for known device overrides first (Logitech mice often report as keyboards)
        if self.vendor_id == 0x046D:  # Logitech
            # Known mice PIDs
            LOGITECH_MICE_PIDS = {
                0xB023, 0x4082,  # MX Master 3
                0xB024, 0x408E,  # MX Master 3S
                0xB034, 0x4093,  # MX Master 3S for Business
                0xB019, 0x4069,  # MX Anywhere 3
                0xB012, 0x4060,  # MX Anywhere 2S
                0xB010, 0x4056,  # MX Anywhere 2
                0xB35B, 0x408A, 0xB35F,  # MX Keys (mouse component of combo)
                0xB367, 0x4096,  # MX Ergo
                0xB369,  # Note: B369 is MX Keys Mini (keyboard)
                0xB36B,  # MX Ergo Plus
            }
            # Known keyboards PIDs
            LOGITECH_KEYBOARD_PIDS = {
                0xB369,  # MX Keys Mini
                0xB35B, 0x408A, 0xB35F,  # MX Keys (keyboard)
                0xB367, 0x4096,  # MX Keys for Mac
            }
            
            # Product name heuristics
            if self.product:
                product_lower = self.product.lower()
                if any(term in product_lower for term in ['master', 'anywhere', 'ergo']) and 'keys' not in product_lower:
                    return "mouse"
                if 'keys' in product_lower or 'keyboard' in product_lower:
                    return "keyboard"
            
            # PID-based override
            if self.product_id in LOGITECH_MICE_PIDS and self.product_id not in LOGITECH_KEYBOARD_PIDS:
                return "mouse"
            if self.product_id in LOGITECH_KEYBOARD_PIDS:
                return "keyboard"
        
        # Fall back to HID usage tables
        if self.usage_page == 0x01:  # Generic Desktop
            if self.usage == 0x02:
                return "mouse"
            elif self.usage == 0x06:
                return "keyboard"
            elif self.usage == 0x04:
                return "joystick"
            elif self.usage == 0x05:
                return "gamepad"
            elif self.usage == 0x08:
                return "multiaxis"
            elif self.usage == 0x80:
                return "system_control"
        elif self.usage_page == 0x0C:  # Consumer
            return "remote"
        elif self.usage_page == 0x0D:  # Digitizer
            if self.usage == 0x01:
                return "digitizer"
            elif self.usage == 0x02:
                return "pen"
            elif self.usage == 0x04:
                return "touchscreen"
        return "unknown"

    @property
    def is_builtin(self) -> bool:
        """
        Detect if device is internal (built-in to laptop).
        
        Strategies (in order of reliability):
        1. Check Built property in IORegistry (if available)
        2. Check LocationID patterns (internal devices have specific ranges)
        3. Match against known Apple internal device PIDs
        4. Check product name for "Internal" keyword
        """
        # Strategy 1: Explicit built property
        if self.built is not None:
            return self.built
        
        # Strategy 2: LocationID patterns
        # Internal devices typically have LocationID in specific range
        if self.location_id is not None:
            # MacBook internal devices often have LocationID like 0x14xxx or 0x15xxx
            # This is hardware-specific and may need adjustment
            if 0x14000000 <= self.location_id <= 0x15ffffff:
                return True
        
        # Strategy 3: Known Apple internal devices
        APPLE_INTERNAL_PIDS = {
            0x0273,  # Internal Keyboard/Trackpad (MacBook Pro)
            0x0274,  # Internal Keyboard/Trackpad (MacBook Air)
            0x0291,  # Internal Keyboard/Trackpad (newer models)
            0x0292,  # Internal Keyboard/Trackpad (M1 models)
            0x0293,  # Internal Keyboard/Trackpad (M2 models)
        }
        if self.vendor_id == 0x05AC:  # Apple
            if self.product_id in APPLE_INTERNAL_PIDS:
                return True
            # Also check product name
            if self.product and "Internal" in self.product:
                return True
            # Check manufacturer for "Apple Internal"
            if self.manufacturer and "Apple Internal" in self.manufacturer:
                return True
        
        # Strategy 4: Transport hints
        if self.transport:
            if "Internal" in self.transport:
                return True
        
        return False


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("macOS-specific feature not available on this platform")


def _run_ioreg() -> bytes:
    try:
        result = subprocess.run(
            ["/usr/sbin/ioreg", "-lw0", "-r", "-c", "IOHIDDevice", "-a"],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - requires macOS tooling
        raise RuntimeError("ioreg not found; install Xcode command line tools") from exc
    return result.stdout


def _coerce_int(value: object) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            if value.lower().startswith("0x"):
                return int(value, 16)
            return int(value)
        except ValueError:
            return None
    return None


def _parse_devices(blob: bytes) -> Iterable[HIDDevice]:
    try:
        payload = plistlib.loads(blob)
    except Exception as exc:  # pragma: no cover - malformed plist
        raise RuntimeError(f"Unable to parse ioreg output: {exc}") from exc

    if not isinstance(payload, list):
        return []

    devices: List[HIDDevice] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        vendor = _coerce_int(entry.get("VendorID"))
        product = _coerce_int(entry.get("ProductID"))
        if vendor is None or product is None:
            continue
        
        # Extract usage page and usage for device type detection
        usage_page = _coerce_int(entry.get("DeviceUsagePage") or entry.get("PrimaryUsagePage"))
        usage = _coerce_int(entry.get("DeviceUsage") or entry.get("PrimaryUsage"))
        
        # Check if device is built-in (Apple internal devices)
        built = entry.get("Built")
        if built is not None and not isinstance(built, bool):
            built = bool(built)
        
        devices.append(
            HIDDevice(
                vendor_id=vendor,
                product_id=product,
                transport=entry.get("Transport"),
                manufacturer=entry.get("Manufacturer"),
                product=entry.get("Product"),
                serial_number=entry.get("SerialNumber"),
                location_id=_coerce_int(entry.get("LocationID")),
                usage_page=usage_page,
                usage=usage,
                built=built,
            )
        )
    return devices


def list_hid_devices(vendor_id: Optional[int] = None) -> List[HIDDevice]:
    """Return IOHIDDevice entries, optionally filtered by vendor id."""

    _require_macos()
    blob = _run_ioreg()
    devices = list(_parse_devices(blob))
    if vendor_id is None:
        return devices
    return [device for device in devices if device.vendor_id == vendor_id]


LOGITECH_VENDOR_ID = 0x046D


def list_logitech_devices() -> List[HIDDevice]:
    """Convenience helper filtered to Logitech devices."""

    return list_hid_devices(LOGITECH_VENDOR_ID)


def build_report_plist(report_id: int, report_bytes: bytes, *, report_type: str = "feature") -> bytes:
    """Create a property list suitable for ``hidutil report``.

    ``hidutil`` expects a dictionary with ``ReportID``, ``ReportType`` and the
    raw bytes encoded as a list of integers. The infamous Easy-Switch feature
    report IDs are vendor-specific; callers must provide valid payloads.
    """

    data = {
        "ReportType": report_type,
        "ReportID": report_id,
        "Report": {"Data": list(report_bytes)},
    }
    return plistlib.dumps(data)


def run_hidutil_report(match: dict, report: bytes) -> subprocess.CompletedProcess:
    """Invoke ``hidutil report`` with the provided match/report dictionaries.

    This API is intentionally low-level; it provides a surfaced hook for future
    experiments once the correct vendor commands are known. At the time of
    writing Logitech has not published the Easy-Switch feature report format, so
    callers must reverse engineer it or use Logitech Options instead.
    """

    _require_macos()
    matching_plist = plistlib.dumps(match)
    try:
        result = subprocess.run(
            [
                "/usr/bin/hidutil",
                "report",
                "--matching",
                matching_plist.decode("utf-8"),
                "--report",
                report.decode("utf-8"),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - requires macOS tooling
        raise RuntimeError("hidutil not found; install Xcode command line tools") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        message = stderr or stdout or "hidutil report failed"
        raise RuntimeError(message) from exc
    return result


def build_hidpp_short_command(
    feature: int,
    function: int,
    params: Sequence[int] = (),
    *,
    device_index: int = 0x02,
) -> bytes:
    """Build a HID++ short message payload (7 bytes)."""

    if len(params) > 3:
        raise ValueError("HID++ short command accepts at most three parameters")
    payload = [0x10, device_index & 0xFF, feature & 0xFF, function & 0xFF]
    payload.extend(int(p) & 0xFF for p in params)
    while len(payload) < 7:
        payload.append(0x00)
    return bytes(payload)


def _infer_device_index(device: HIDDevice) -> int:
    transport = (device.transport or "").lower()
    if transport.startswith("usb"):
        return 0x01
    return 0x02


def easy_switch_payload(slot: int, *, device_index: int = 0x02) -> bytes:
    """Return the HID++ payload used to change Easy-Switch host slots."""

    if slot not in (1, 2, 3):
        raise ValueError("Easy-Switch slot must be 1, 2, or 3")
    return build_hidpp_short_command(0x63, 0x01, (slot,), device_index=device_index)


def easy_switch_select_host(
    device: HIDDevice,
    slot: int,
    *,
    device_index: Optional[int] = None,
    dry_run: bool = False,
):
    """Switch a Logitech Easy-Switch device to the requested host slot."""

    _require_macos()
    resolved_index = device_index if device_index is not None else _infer_device_index(device)
    payload = easy_switch_payload(slot, device_index=resolved_index)
    report = build_report_plist(0x10, payload)
    matching = device.matching_dict()
    if dry_run:
        return {"matching": matching, "payload": payload, "method": "hidutil"}
    try:
        return run_hidutil_report(matching, report)
    except RuntimeError as exc:
        if _should_fallback_to_hidapi(str(exc)):
            LOG.debug("Falling back to hidapi for Easy-Switch command: %s", exc)
            try:
                return _easy_switch_via_hidapi(device, payload)
            except RuntimeError as hid_exc:
                LOG.debug("hidapi fallback failed: %s", hid_exc)
                # Try sending as an OUTPUT report over the Logitech vendor interface (BLE path)
                output_exc = None
                try:
                    return _easy_switch_via_hidapi_output(device, slot)
                except RuntimeError as _output_exc:
                    output_exc = _output_exc
                    LOG.debug("hidapi output-report fallback failed: %s", output_exc)
                
                # Try IOKit OUTPUT report approach for BLE devices (SwitchMX approach)
                try:
                    return _easy_switch_via_iokit_ble(device, slot)
                except RuntimeError as iokit_exc:
                        error_parts = [
                            f"hidutil unsupported ({exc})",
                            f"hidapi feature failed ({hid_exc})",
                            f"hidapi output failed ({output_exc})",
                            f"IOKit BLE failed ({iokit_exc})"
                        ]
    
                        # Build helpful error message
                        error_msg = "Unable to send Easy-Switch command: " + "; ".join(error_parts)
    
                        # Add guidance for BLE devices
                        if device.transport and "bluetooth" in device.transport.lower():
                            error_msg += (
                                "\n\n"
                                "⚠️  Bluetooth Easy-Switch Troubleshooting:\n"
                                "\n"
                                "✅ Alternative Solutions:\n"
                                "   1. Ensure device is paired and connected to this Mac\n"
                                "   2. Try using a Logitech USB Unifying or Bolt receiver:\n"
                                "      - Plug in a receiver and pair your device to it\n"
                                "      - Run: silta capabilities switch --slot N --product-id 0xC52B\n"
                                "   3. Use Logitech Options+ application (free from Logitech)\n"
                                "   4. Press the physical Easy-Switch button on your device\n"
                                "\n"
                                "📚 References:\n"
                                "   - SwitchMX: https://github.com/boyvanamstel/SwitchMX (Bluetooth approach)\n"
                                "   - logiSwitch: https://github.com/nicoduj/logiSwitch (USB receiver approach)\n"
                            )
    
                        raise RuntimeError(error_msg) from iokit_exc
        raise


def _should_fallback_to_hidapi(message: str) -> bool:
    lowered = message.lower()
    if "unknown command" in lowered and "report" in lowered:
        return True
    if "hidutil not found" in lowered:
        return True
    return False


def _easy_switch_via_hidapi(device: HIDDevice, payload: bytes):
    try:
        import hid  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "hidutil does not support the 'report' command on this system and the 'hid' package is not installed. "
            "Install hidapi support with 'python -m pip install hid' and ensure the hidapi library is available (e.g. 'brew install hidapi')."
        ) from exc

    matches = hid.enumerate(device.vendor_id, device.product_id)  # type: ignore[attr-defined]
    target = None
    
    # Prefer the Logitech vendor-specific interface (usage_page=0xff43) for HID++ commands
    for entry in matches:
        usage_page = entry.get("usage_page", 0)
        serial = entry.get("serial_number")
        
        # Check if this is the vendor-specific interface
        if usage_page == 0xff43:
            if device.serial_number and serial:
                if str(serial) == str(device.serial_number):
                    target = entry
                    break
            elif target is None or target.get("usage_page") != 0xff43:
                target = entry
        # Fallback to any matching device if no vendor-specific interface found
        elif target is None and not device.serial_number:
            target = entry
        elif device.serial_number and serial and str(serial) == str(device.serial_number):
            if target is None:
                target = entry

    if target is None:
        raise RuntimeError("hidapi could not locate the Easy-Switch device")

    try:
        dev = hid.Device(path=target.get("path"))  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - depends on HID state
        # Fallback: try opening by vid/pid[/serial]
        try:
            serial = target.get("serial_number") or device.serial_number
            if serial:
                dev = hid.Device(vid=device.vendor_id, pid=device.product_id, serial=str(serial))  # type: ignore[attr-defined]
            else:
                dev = hid.Device(vid=device.vendor_id, pid=device.product_id)  # type: ignore[attr-defined]
        except Exception as exc2:
            raise RuntimeError(
                f"hidapi could not open the device: fallback error: {exc2}; original error: {exc}"
            ) from exc2

    try:
        sent = dev.send_feature_report(payload)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - depends on HID state
        raise RuntimeError(f"hidapi failed to send feature report: {exc}") from exc
    finally:
        try:
            dev.close()  # type: ignore[attr-defined]
        except Exception:
            pass

    if sent <= 0:
        raise RuntimeError("hidapi did not report any bytes written")

    return {"method": "hidapi", "bytes_written": sent, "path": target.get("path")}


def _build_ble_output_candidates(slot: int) -> List[bytes]:
    """Return a list of candidate BLE HID++ output reports for Easy-Switch.

    Based on proven approach from SwitchMX (https://github.com/boyvanamstel/SwitchMX):
        [0x11, 0xFF, 0x0a, 0x1b, channel, 0x00, ... (pad to 20 bytes)]

    Where channel is 0,1,2 for buttons 1,2,3. The payload format is:
    - Byte 0: Report ID (0x11 for long HID++ report)
    - Byte 1: Device index (0xFF for BLE devices)
    - Byte 2-3: Feature/function identifiers (0x0a, 0x1b observed working)
    - Byte 4: Channel/slot index (0-based)
    - Remaining bytes: Padding (0x00)

    Community knowledge (input-switcher/Solaar) indicates alternate values:
    C in {0x09, 0x0A, 0x0C} and D in {0x1B, 0x1C, 0x1E} for various models.
    """

    if slot not in (1, 2, 3):
        raise ValueError("Easy-Switch slot must be 1, 2, or 3")

    channel = (slot - 1) & 0xFF
    candidates: List[bytes] = []
    
    # Primary format from SwitchMX (proven working for MX Master 3S)
    payload = [0x11, 0xFF, 0x0A, 0x1B, channel]
    while len(payload) < 20:
        payload.append(0x00)
    candidates.append(bytes(payload))
    
    # Alternate C/D values for other device models
    c_values = (0x09, 0x0A, 0x0C)
    d_values = (0x1B, 0x1C, 0x1E)

    for c in c_values:
        for d in d_values:
            if c == 0x0A and d == 0x1B:
                continue  # Already added as primary candidate
            payload = [0x11, 0xFF, c & 0xFF, d & 0xFF, channel]
            while len(payload) < 20:
                payload.append(0x00)
            candidates.append(bytes(payload))

    # Some reports indicate certain devices may accept a short 7-byte variant
    # over BLE. Try a couple of common C/D pairs as a last resort.
    for c in c_values:
        for d in d_values:
            candidates.append(bytes([0x11, 0xFF, c & 0xFF, d & 0xFF, channel, 0x00, 0x00]))

    return candidates


def _easy_switch_via_hidapi_output(device: HIDDevice, slot: int):
    """Attempt Easy-Switch via hidapi OUTPUT report to the vendor interface.

    Targets the Logitech vendor-specific BLE interface (usage_page=0xFF43,
    usage=0x0202) and sends candidate 0x11 output reports. Returns on the first
    successful write (>0 bytes) or raises with details of attempts.
    """
    try:
        import hid  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "hid output-report path requires 'hid' package. Install with 'python -m pip install hid'."
        ) from exc

    matches = hid.enumerate(device.vendor_id, device.product_id)  # type: ignore[attr-defined]
    # Choose BLE vendor interface if present
    targets = []
    for entry in matches:
        if entry.get("usage_page") == 0xFF43 and entry.get("usage") == 0x0202:
            if device.serial_number and entry.get("serial_number"):
                if str(entry.get("serial_number")) == str(device.serial_number):
                    targets = [entry]
                    break
            targets.append(entry)

    if not targets:
        # As a fallback, accept any 0xFF43 interface for this device
        for entry in matches:
            if entry.get("usage_page") == 0xFF43:
                targets.append(entry)

    if not targets:
        # Last resort: try any interface enumerated for this VID/PID
        targets = list(matches)

    if not targets:
        raise RuntimeError("hidapi could not locate any interface for this device")

    attempts = []
    candidates = _build_ble_output_candidates(slot)
    last_exc: Optional[Exception] = None

    for target in targets:
        dev = None
        try:
            # Prefer opening by path
            path = target.get("path")
            if path:
                try:
                    dev = hid.Device(path=path)  # type: ignore[attr-defined]
                except Exception as exc:
                    last_exc = exc
                    dev = None
            # Fallback: try opening by vid/pid (+serial if available)
            if dev is None:
                serial = target.get("serial_number") or device.serial_number
                try:
                    if serial:
                        dev = hid.Device(vid=device.vendor_id, pid=device.product_id, serial=str(serial))  # type: ignore[attr-defined]
                    else:
                        dev = hid.Device(vid=device.vendor_id, pid=device.product_id)  # type: ignore[attr-defined]
                except Exception as exc:
                    last_exc = exc
                    dev = None
            if dev is None:
                continue

            for payload in candidates:
                try:
                    # hidapi write expects the first byte to be report id
                    written = dev.write(payload)  # type: ignore[attr-defined]
                    attempts.append({
                        "path": target.get("path"),
                        "usage_page": target.get("usage_page"),
                        "usage": target.get("usage"),
                        "bytes": list(payload),
                        "written": int(written) if written is not None else -1,
                    })
                    if written and written > 0:
                        return {
                            "method": "hidapi-output",
                            "bytes_written": int(written),
                            "path": target.get("path"),
                        }
                except Exception as exc:  # pragma: no cover - device dependent
                    last_exc = exc
                    continue
        finally:
            if dev is not None:
                try:
                    dev.close()  # type: ignore[attr-defined]
                except Exception:
                    pass

    detail = "no bytes written"
    if last_exc is not None:
        detail = f"last error: {last_exc}"
    raise RuntimeError(f"hidapi output attempts failed ({detail}); attempts={len(attempts)}")


_IOKIT = None
_COREFOUNDATION = None


def _load_framework(name: str):
    path = util.find_library(name)
    if not path:
        raise RuntimeError(f"Unable to locate framework: {name}")
    return ctypes.CDLL(path, use_errno=True)


def _get_iokit():
    global _IOKIT
    if _IOKIT is None:
        _IOKIT = _load_framework("IOKit")
    return _IOKIT


def _get_corefoundation():
    global _COREFOUNDATION
    if _COREFOUNDATION is None:
        _COREFOUNDATION = _load_framework("CoreFoundation")
    return _COREFOUNDATION


def _easy_switch_via_iokit_ble(device: HIDDevice, slot: int):  # pragma: no cover - mac-only path
    """Attempt Easy-Switch via IOKit OUTPUT report for BLE devices.
    
    Based on proven approach from SwitchMX (https://github.com/boyvanamstel/SwitchMX).
    Uses OUTPUT report type (kIOHIDReportTypeOutput) instead of FEATURE reports,
    and targets the Logitech vendor-specific BLE interface (usagePage=0xFF43, usage=0x0202).
    """
    IOKit = _get_iokit()
    CF = _get_corefoundation()

    kCFAllocatorDefault = ctypes.c_void_p.in_dll(CF, "kCFAllocatorDefault")
    kCFStringEncodingUTF8 = 0x08000100
    kCFNumberSInt32Type = 3
    kIOHIDReportTypeOutput = 1  # OUTPUT report (per SwitchMX) - different from FEATURE (2)
    kIOHIDOptionsTypeNone = 0x0
    
    # Build SwitchMX-style payload: [0x11, 0xFF, 0x0A, 0x1B, channel, padding...]
    channel = (slot - 1) & 0xFF
    payload = [0x11, 0xFF, 0x0A, 0x1B, channel]
    while len(payload) < 20:
        payload.append(0x00)
    payload_bytes = bytes(payload)

    CFStringCreateWithCString = CF.CFStringCreateWithCString
    CFStringCreateWithCString.restype = ctypes.c_void_p
    CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]

    CFNumberCreate = CF.CFNumberCreate
    CFNumberCreate.restype = ctypes.c_void_p
    CFNumberCreate.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]

    CFDictionarySetValue = CF.CFDictionarySetValue
    CFDictionarySetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]

    CFRelease = CF.CFRelease
    CFRelease.argtypes = [ctypes.c_void_p]

    CFStringGetCStringPtr = CF.CFStringGetCStringPtr
    CFStringGetCStringPtr.restype = ctypes.c_char_p
    CFStringGetCStringPtr.argtypes = [ctypes.c_void_p, ctypes.c_uint32]

    CFStringGetCString = CF.CFStringGetCString
    CFStringGetCString.restype = ctypes.c_bool
    CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint32]

    IOServiceMatching = IOKit.IOServiceMatching
    IOServiceMatching.restype = ctypes.c_void_p
    IOServiceMatching.argtypes = [ctypes.c_char_p]

    IOServiceGetMatchingServices = IOKit.IOServiceGetMatchingServices
    IOServiceGetMatchingServices.restype = ctypes.c_int
    IOServiceGetMatchingServices.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]

    IOIteratorNext = IOKit.IOIteratorNext
    IOIteratorNext.restype = ctypes.c_uint32
    IOIteratorNext.argtypes = [ctypes.c_uint32]

    IOObjectRelease = IOKit.IOObjectRelease
    IOObjectRelease.restype = ctypes.c_int
    IOObjectRelease.argtypes = [ctypes.c_uint32]

    IORegistryEntryCreateCFProperty = IOKit.IORegistryEntryCreateCFProperty
    IORegistryEntryCreateCFProperty.restype = ctypes.c_void_p
    IORegistryEntryCreateCFProperty.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]

    IOHIDDeviceCreate = IOKit.IOHIDDeviceCreate
    IOHIDDeviceCreate.restype = ctypes.c_void_p
    IOHIDDeviceCreate.argtypes = [ctypes.c_void_p, ctypes.c_uint32]

    IOHIDDeviceOpen = IOKit.IOHIDDeviceOpen
    IOHIDDeviceOpen.restype = ctypes.c_int
    IOHIDDeviceOpen.argtypes = [ctypes.c_void_p, ctypes.c_uint32]

    IOHIDDeviceSetReport = IOKit.IOHIDDeviceSetReport
    IOHIDDeviceSetReport.restype = ctypes.c_int
    IOHIDDeviceSetReport.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]

    IOHIDDeviceClose = IOKit.IOHIDDeviceClose
    IOHIDDeviceClose.restype = ctypes.c_int
    IOHIDDeviceClose.argtypes = [ctypes.c_void_p, ctypes.c_uint32]

    matching = IOServiceMatching(b"IOHIDDevice")
    if not matching:
        raise RuntimeError("IOServiceMatching failed")

    def _set_int_key(dict_ref, key_name: bytes, value: int):
        key = CFStringCreateWithCString(kCFAllocatorDefault, key_name, kCFStringEncodingUTF8)
        if not key:
            raise RuntimeError("CFStringCreateWithCString failed")
        number_value = ctypes.c_int32(value)
        cf_number = CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt32Type, ctypes.byref(number_value))
        if not cf_number:
            CFRelease(key)
            raise RuntimeError("CFNumberCreate failed")
        CFDictionarySetValue(dict_ref, key, cf_number)
        CFRelease(key)
        CFRelease(cf_number)

    _set_int_key(matching, b"VendorID", device.vendor_id)
    _set_int_key(matching, b"ProductID", device.product_id)
    _set_int_key(matching, b"DeviceUsagePage", 0xFF43)  # Logitech BLE HID++ interface
    _set_int_key(matching, b"DeviceUsage", 0x0202)      # HID++ protocol over BLE

    iterator = ctypes.c_uint32()
    kr = IOServiceGetMatchingServices(0, matching, ctypes.byref(iterator))
    if kr != 0:
        raise RuntimeError(f"IOServiceGetMatchingServices failed ({kr})")

    try:
        while True:
            service = IOIteratorNext(iterator.value)
            if not service:
                break
            try:
                if device.serial_number:
                    serial_key = CFStringCreateWithCString(kCFAllocatorDefault, b"SerialNumber", kCFStringEncodingUTF8)
                    if serial_key:
                        cf_serial = IORegistryEntryCreateCFProperty(service, serial_key, kCFAllocatorDefault, 0)
                        CFRelease(serial_key)
                        serial_value = None
                        if cf_serial:
                            serial_value = _cfstring_to_str(cf_serial, CFStringGetCStringPtr, CFStringGetCString, kCFStringEncodingUTF8)
                            CFRelease(cf_serial)
                        if serial_value and serial_value != str(device.serial_number):
                            continue

                device_ref = IOHIDDeviceCreate(kCFAllocatorDefault, service)
                if not device_ref:
                    continue
                try:
                    kr = IOHIDDeviceOpen(device_ref, kIOHIDOptionsTypeNone)
                    if kr != 0:
                        continue
                    try:
                        buffer = (ctypes.c_uint8 * len(payload_bytes))(*payload_bytes)
                        report_id = ctypes.c_uint32(payload_bytes[0]) if payload_bytes else ctypes.c_uint32(0)
                        kr = IOHIDDeviceSetReport(device_ref, kIOHIDReportTypeOutput, report_id, buffer, len(payload_bytes))
                        if kr != 0:
                            raise RuntimeError(f"IOHIDDeviceSetReport failed ({kr})")
                        return {"method": "iokit-ble", "bytes_written": len(payload_bytes)}
                    finally:
                        IOHIDDeviceClose(device_ref, kIOHIDOptionsTypeNone)
                finally:
                    CFRelease(device_ref)
            finally:
                IOObjectRelease(service)
    finally:
        IOObjectRelease(iterator.value)

    raise RuntimeError("IOKit could not find or program the Easy-Switch device")


def _cfstring_to_str(cf_string, get_ptr, get_cstring, encoding):
    if not cf_string:
        return None
    c_ptr = get_ptr(cf_string, encoding)
    if c_ptr:
        return ctypes.cast(c_ptr, ctypes.c_char_p).value.decode("utf-8")
    buffer = ctypes.create_string_buffer(256)
    if get_cstring(cf_string, buffer, len(buffer), encoding):
        return buffer.value.decode("utf-8")
    CF = _get_corefoundation()
    CFStringGetLength = CF.CFStringGetLength
    CFStringGetLength.restype = ctypes.c_long
    CFStringGetLength.argtypes = [ctypes.c_void_p]
    length = CFStringGetLength(cf_string)
    if length <= 0:
        return None
    size = (length + 1) * 4
    buffer = ctypes.create_string_buffer(size)
    if get_cstring(cf_string, buffer, size, encoding):
        return buffer.value.decode("utf-8")
    return None
