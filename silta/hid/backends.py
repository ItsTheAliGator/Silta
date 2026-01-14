from __future__ import annotations

import ctypes
import plistlib
import subprocess
import sys
from ctypes import util
from typing import List, Optional

from .device import HIDDevice
from silta.utils import LOG

def _require_macos() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("macOS-specific feature not available on this platform")

def build_report_plist(report_id: int, report_bytes: bytes, *, report_type: str = "feature") -> bytes:
    data = {
        "ReportType": report_type,
        "ReportID": report_id,
        "Report": {"Data": list(report_bytes)},
    }
    return plistlib.dumps(data)

def run_hidutil_report(match: dict, report: bytes) -> subprocess.CompletedProcess:
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
    except FileNotFoundError as exc:
        raise RuntimeError("hidutil not found; install Xcode command line tools") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        message = stderr or stdout or "hidutil report failed"
        raise RuntimeError(message) from exc
    return result

def easy_switch_via_hidapi(device: HIDDevice, payload: bytes):
    try:
        import hid  # type: ignore
    except ImportError as exc:
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
        if usage_page == 0xff43:
            if device.serial_number and serial:
                if str(serial) == str(device.serial_number):
                    target = entry
                    break
            elif target is None or target.get("usage_page") != 0xff43:
                target = entry
        elif target is None and not device.serial_number:
            target = entry
        elif device.serial_number and serial and str(serial) == str(device.serial_number):
            if target is None:
                target = entry

    if target is None:
        raise RuntimeError("hidapi could not locate the Easy-Switch device")

    try:
        dev = hid.Device(path=target.get("path"))  # type: ignore[attr-defined]
    except Exception as exc:
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
    except Exception as exc:
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
    if slot not in (1, 2, 3):
        raise ValueError("Easy-Switch slot must be 1, 2, or 3")

    channel = (slot - 1) & 0xFF
    candidates: List[bytes] = []
    
    # Primary format from SwitchMX
    payload = [0x11, 0xFF, 0x0A, 0x1B, channel]
    while len(payload) < 20:
        payload.append(0x00)
    candidates.append(bytes(payload))
    
    c_values = (0x09, 0x0A, 0x0C)
    d_values = (0x1B, 0x1C, 0x1E)

    for c in c_values:
        for d in d_values:
            if c == 0x0A and d == 0x1B:
                continue
            payload = [0x11, 0xFF, c & 0xFF, d & 0xFF, channel]
            while len(payload) < 20:
                payload.append(0x00)
            candidates.append(bytes(payload))

    for c in c_values:
        for d in d_values:
            candidates.append(bytes([0x11, 0xFF, c & 0xFF, d & 0xFF, channel, 0x00, 0x00]))

    return candidates

def easy_switch_via_hidapi_output(device: HIDDevice, slot: int):
    try:
        import hid  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "hid output-report path requires 'hid' package. Install with 'python -m pip install hid'."
        ) from exc

    matches = hid.enumerate(device.vendor_id, device.product_id)  # type: ignore[attr-defined]
    targets = []
    for entry in matches:
        if entry.get("usage_page") == 0xFF43 and entry.get("usage") == 0x0202:
            if device.serial_number and entry.get("serial_number"):
                if str(entry.get("serial_number")) == str(device.serial_number):
                    targets = [entry]
                    break
            targets.append(entry)

    if not targets:
        for entry in matches:
            if entry.get("usage_page") == 0xFF43:
                targets.append(entry)

    if not targets:
        targets = list(matches)

    if not targets:
        raise RuntimeError("hidapi could not locate any interface for this device")

    attempts = []
    candidates = _build_ble_output_candidates(slot)
    last_exc: Optional[Exception] = None

    for target in targets:
        dev = None
        try:
            path = target.get("path")
            if path:
                try:
                    dev = hid.Device(path=path)  # type: ignore[attr-defined]
                except Exception as exc:
                    last_exc = exc
                    dev = None
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
                    written = dev.write(payload)  # type: ignore[attr-defined]
                    attempts.append({
                        "path": target.get("path"),
                        "bytes": list(payload),
                        "written": int(written) if written is not None else -1,
                    })
                    if written and written > 0:
                        return {
                            "method": "hidapi-output",
                            "bytes_written": int(written),
                            "path": target.get("path"),
                        }
                except Exception as exc:
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

def easy_switch_via_iokit_ble(device: HIDDevice, slot: int):
    if slot not in (1, 2, 3):
        raise ValueError("Easy-Switch slot must be 1, 2, or 3")

    IOKit = _get_iokit()
    CF = _get_corefoundation()

    kCFAllocatorDefault = ctypes.c_void_p.in_dll(CF, "kCFAllocatorDefault")
    kCFStringEncodingUTF8 = 0x08000100
    kCFNumberSInt32Type = 3
    kIOHIDReportTypeOutput = 1
    kIOHIDOptionsTypeNone = 0x0
    
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
    _set_int_key(matching, b"DeviceUsagePage", 0xFF43)
    _set_int_key(matching, b"DeviceUsage", 0x0202)

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
