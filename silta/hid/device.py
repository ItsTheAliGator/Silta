from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional, Set

# Attempt to import LOG from silta.utils (module or package)
try:
    from silta.utils import LOG
except ImportError:
    import logging
    LOG = logging.getLogger("silta.hid")

def _load_device_data() -> dict:
    """Load externalized device PIDs from JSON."""
    # This file is at silta/hid/device.py
    # We want silta/data/logitech_devices.json
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(base_dir, "data", "logitech_devices.json")
    try:
        if os.path.exists(data_path):
            with open(data_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        LOG.debug("Failed to load device data from %s: %s", data_path, exc)
    return {"mice": [], "keyboards": []}

_DEVICE_DATA = _load_device_data()

def _parse_hex_pids(hex_strings: list[str]) -> Set[int]:
    pids = set()
    for s in hex_strings:
        try:
            pids.add(int(s, 16))
        except ValueError:
            pass
    return pids

_LOGITECH_MICE_PIDS = _parse_hex_pids(_DEVICE_DATA.get("mice", []))
_LOGITECH_KEYBOARD_PIDS = _parse_hex_pids(_DEVICE_DATA.get("keyboards", []))

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
        """
        # Check for known device overrides first (Logitech mice often report as keyboards)
        if self.vendor_id == 0x046D:  # Logitech
            # Product name heuristics
            if self.product:
                product_lower = self.product.lower()
                if any(term in product_lower for term in ['master', 'anywhere', 'ergo']) and 'keys' not in product_lower:
                    return "mouse"
                if 'keys' in product_lower or 'keyboard' in product_lower:
                    return "keyboard"
            
            # PID-based override
            if self.product_id in _LOGITECH_MICE_PIDS and self.product_id not in _LOGITECH_KEYBOARD_PIDS:
                return "mouse"
            if self.product_id in _LOGITECH_KEYBOARD_PIDS:
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
        """
        # Strategy 1: Explicit built property
        if self.built is not None:
            return self.built
        
        # Strategy 2: LocationID patterns
        # Internal devices typically have LocationID in specific range
        if self.location_id is not None:
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
