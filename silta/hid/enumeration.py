from __future__ import annotations

import plistlib
import subprocess
import sys
from typing import List

from .device import HIDDevice
from silta.utils import LOG

def list_hid_devices() -> List[HIDDevice]:
    if sys.platform != "darwin":
        return []
    
    try:
        data = _run_ioreg()
    except Exception as exc:
        LOG.error("Failed to list HID devices via ioreg: %s", exc)
        return []
    
    return _parse_devices(data)

def _run_ioreg() -> bytes:
    # Run ioreg -a -r -c IOHIDDevice -l
    result = subprocess.run(
        ["ioreg", "-a", "-r", "-c", "IOHIDDevice", "-l"],
        capture_output=True,
        check=True,
        timeout=30  # seconds
    )
    return result.stdout

def _parse_devices(plist_data: bytes) -> List[HIDDevice]:
    if not plist_data:
        return []

    try:
        items = plistlib.loads(plist_data)
    except Exception as exc:
        LOG.error("Failed to parse ioreg plist: %s", exc)
        return []

    devices = []
    # ioreg returns a list of dictionaries (one per IOHIDDevice tree) or a dict if single root?
    # Usually a list of objects matching IOHIDDevice.
    # However, sometimes it's nested. Based on -r (recursive), it might be a tree.
    # But -c IOHIDDevice finds those specifically.
    
    if isinstance(items, dict):
        items = [items]
        
    for item in items:
        # We might need to traverse if it's a tree, but with -c IOHIDDevice it usually gives the nodes directly
        # or minimal nesting.
        if isinstance(item, dict):
            _extract_device(item, devices)
        
    return devices

def _extract_device(node: dict, devices: List[HIDDevice]) -> None:
    # Check if this node looks like a HID device
    vid = node.get("VendorID")
    pid = node.get("ProductID")
    
    if isinstance(vid, int) and isinstance(pid, int):
        transport = node.get("Transport")
        manufacturer = node.get("Manufacturer")
        product = node.get("Product")
        serial = node.get("SerialNumber")
        location = node.get("LocationID")
        usage = node.get("PrimaryUsage")
        usage_page = node.get("PrimaryUsagePage")
        built = node.get("Built-In")

        # Normalize serial number (sometimes it's an integer or bytes in some plist versions)
        if isinstance(serial, (int, float)):
            serial = str(int(serial))
        
        dev = HIDDevice(
            vendor_id=vid,
            product_id=pid,
            transport=transport,
            manufacturer=manufacturer,
            product=product,
            serial_number=serial,
            location_id=location,
            usage=usage,
            usage_page=usage_page,
            built=built
        )
        devices.append(dev)

    # Recurse children if any (ioreg -a -r structure)
    # The children key is usually "IORegistryEntryChildren" check specific property though
    # plistlib usually decodes standard structure.
    # Actually, `ioreg -a` output structure puts children in plain list usually?
    # Let's inspect how simple Flat parsing works in original code.
    # Original code just iterated the list from `ioreg -a -l -r -n IOHIDDevice`.
    # Assuming flat list or simple recursion is enough.
    
    # Original implementation didn't strictly recurse for *nested* HID devices but handled the top level list.
    # However, some devices (like receivers) have children.
    # We'll just check children key just in case.
    children = node.get("IORegistryEntryChildren")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                _extract_device(child, devices)
