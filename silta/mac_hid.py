"""macOS HID helpers for experimental host switching research.

This module provides lightweight wrappers around ``ioreg`` output so we can
enumerate Logitech MX devices and experiment with vendor-specific reports.
It does **not** implement Easy-Switch host swapping because Logitech has not
published the required HID feature reports.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass
class HIDDevice:
    vendor_id: int
    product_id: int
    transport: Optional[str]
    manufacturer: Optional[str]
    product: Optional[str]
    serial_number: Optional[str]
    location_id: Optional[int]

    def matching_dict(self) -> dict:
        """Return an ``hidutil`` matching dictionary for the device."""

        match = {"VendorID": self.vendor_id, "ProductID": self.product_id}
        if self.serial_number:
            match["SerialNumber"] = self.serial_number
        return match


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
        devices.append(
            HIDDevice(
                vendor_id=vendor,
                product_id=product,
                transport=entry.get("Transport"),
                manufacturer=entry.get("Manufacturer"),
                product=entry.get("Product"),
                serial_number=entry.get("SerialNumber"),
                location_id=_coerce_int(entry.get("LocationID")),
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
            check=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - requires macOS tooling
        raise RuntimeError("hidutil not found; install Xcode command line tools") from exc
    return result
