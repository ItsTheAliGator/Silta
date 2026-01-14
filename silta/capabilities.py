from __future__ import annotations

"""Capability hints for known keyboards/mice (read-only).

This module provides a small, maintainable mapping from (vendor_id, product_id)
to a set of capability hints. Hints are informational only and do not imply the
ability to control devices.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple
import json

from . import mac_hid


@dataclass(frozen=True)
class Capability:
    key: str
    label: str


# Common capabilities we care about
EASY_SWITCH = Capability("easy_switch", "Easy‑Switch / Multi‑Host")
BLUETOOTH = Capability("bluetooth", "Bluetooth")
UNIFYING = Capability("unifying", "Logitech Unifying Receiver")
LOW_ENERGY = Capability("ble", "Bluetooth LE")
PER_APP_PROFILES = Capability("profiles", "Profiles (Vendor App)")
EASY_SWITCH_CONTROL = Capability("easy_switch_control", "Easy-Switch Host Switching")


# Comprehensive mapping for Logitech devices (based on community research)
# Sources: Solaar, SwitchMX, logiSwitch, Linux USB IDs database
_CAPS: Dict[Tuple[int, int], Set[Capability]] = {
    # === LOGITECH MICE ===
    # MX Master 3 (Mac optimized)
    (0x046D, 0xB023): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x4082): {EASY_SWITCH, UNIFYING, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # Unifying
    
    # MX Master 3 for Business
    (0x046D, 0xB024): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x408E): {EASY_SWITCH, UNIFYING, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # Unifying
    
    # MX Master 3S
    (0x046D, 0xB034): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x4093): {EASY_SWITCH, UNIFYING, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # Unifying
    
    # MX Master 2S
    (0x046D, 0xB019): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x4069): {EASY_SWITCH, UNIFYING, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # Unifying
    
    # MX Master (original)
    (0x046D, 0xB012): {BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES},  # BT
    (0x046D, 0x4060): {UNIFYING, PER_APP_PROFILES},  # Unifying
    
    # MX Anywhere 3
    (0x046D, 0xB027): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x4092): {EASY_SWITCH, UNIFYING, EASY_SWITCH_CONTROL},  # Unifying
    
    # MX Anywhere 3S
    (0x046D, 0xB03C): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x409A): {EASY_SWITCH, UNIFYING, EASY_SWITCH_CONTROL},  # Unifying
    
    # MX Anywhere 2S
    (0x046D, 0xB01A): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x406A): {EASY_SWITCH, UNIFYING, EASY_SWITCH_CONTROL},  # Unifying
    
    # MX Anywhere 2
    (0x046D, 0xB013): {BLUETOOTH, LOW_ENERGY},  # BT
    (0x046D, 0x404A): {UNIFYING},  # Unifying
    
    # MX Ergo
    (0x046D, 0xB01D): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x406F): {EASY_SWITCH, UNIFYING, EASY_SWITCH_CONTROL},  # Unifying
    
    # MX Ergo Plus
    (0x046D, 0xB027): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, EASY_SWITCH_CONTROL},  # BT (same PID as Anywhere 3)
    
    # Lift Vertical Mouse
    (0x046D, 0xB03B): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x4099): {EASY_SWITCH, UNIFYING, EASY_SWITCH_CONTROL},  # Unifying
    
    # Lift for Business
    (0x046D, 0xB03E): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, EASY_SWITCH_CONTROL},  # BT
    
    # === LOGITECH KEYBOARDS ===
    # MX Keys
    (0x046D, 0xB35B): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x408A): {EASY_SWITCH, UNIFYING, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # Unifying
    (0x046D, 0xB35F): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT for Mac
    
    # MX Keys for Business
    (0x046D, 0xB367): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x4096): {EASY_SWITCH, UNIFYING, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # Unifying
    
    # MX Keys Mini
    (0x046D, 0xB369): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x4093): {EASY_SWITCH, UNIFYING, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # Unifying (shared PID)
    
    # MX Keys Mini for Mac
    (0x046D, 0xB36B): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT
    
    # MX Keys S
    (0x046D, 0xB37B): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0xB37C): {EASY_SWITCH, Capability("bolt", "Logitech Bolt"), PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # Bolt
    
    # MX Mechanical
    (0x046D, 0xB35D): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT
    (0x046D, 0x4099): {EASY_SWITCH, UNIFYING, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # Unifying (shared PID)
    
    # MX Mechanical Mini
    (0x046D, 0xB359): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT
    
    # MX Mechanical Mini for Mac
    (0x046D, 0xB35C): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # BT
    
    # K380 Multi-Device
    (0x046D, 0xB342): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, EASY_SWITCH_CONTROL},  # BT
    
    # K380 for Mac
    (0x046D, 0xB34C): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, EASY_SWITCH_CONTROL},  # BT
    
    # === LOGITECH RECEIVERS ===
    (0x046D, 0xC52B): {UNIFYING},  # Unifying Receiver
    (0x046D, 0xC532): {UNIFYING},  # Unifying Receiver (nano)
    (0x046D, 0xC548): {Capability("bolt", "Logitech Bolt Receiver")},  # Bolt Receiver
    
    # === LOGITECH COMBOS ===
    # MX Keys + MX Master 3 Combo
    (0x046D, 0x409F): {EASY_SWITCH, UNIFYING, PER_APP_PROFILES, EASY_SWITCH_CONTROL},  # Combo receiver
}


def capabilities_for(vendor_id: int, product_id: int) -> List[Capability]:
    """Return a sorted list of capability hints for a VID/PID pair."""

    caps = _CAPS.get((vendor_id, product_id), set())
    return sorted(caps, key=lambda c: c.key)


def summarize(device) -> str:
    """Return a short human-readable summary for a HIDDevice-like object."""

    caps = capabilities_for(getattr(device, "vendor_id", 0), getattr(device, "product_id", 0))
    if not caps:
        return "No known special capabilities"
    return ", ".join(c.label for c in caps)


def _hex4(value: int) -> str:
    return f"{int(value) & 0xFFFF:04X}"


def capabilities_keys_for(vendor_id: int, product_id: int) -> List[str]:
    """Return stable capability keys for a VID/PID pair."""

    return [c.key for c in capabilities_for(vendor_id, product_id)]


def export_connected_capabilities_json(path: str, vendor_id: Optional[int] = None) -> Dict[str, dict]:
    """Enumerate connected HID devices and export a grouped capabilities JSON.

    Grouping is by (vendor_id -> product name) and aggregates all PID variants
    observed for that product. Capability keys are the union across variants.

    Returns the JSON-serializable dictionary and writes it to ``path``.
    """

    devices = mac_hid.list_hid_devices(vendor_id)

    vendors: Dict[str, Dict[str, dict]] = {}
    vendor_names: Dict[str, str] = {}

    for dev in devices:
        vid_hex = _hex4(dev.vendor_id)
        pid_hex = _hex4(dev.product_id)
        vbucket = vendors.setdefault(vid_hex, {})
        if vid_hex not in vendor_names and getattr(dev, "manufacturer", None):
            vendor_names[vid_hex] = str(dev.manufacturer)
        pname = dev.product or f"PID {pid_hex}"
        entry = vbucket.setdefault(
            pname,
            {
                "pids": set(),
                "capabilities": set(),
            },
        )
        entry["pids"].add(pid_hex)
        for key in capabilities_keys_for(dev.vendor_id, dev.product_id):
            entry["capabilities"].add(key)

    # Normalize sets to sorted lists and build final structure
    out: Dict[str, dict] = {"vendors": {}}
    for vid_hex, products in vendors.items():
        out["vendors"].setdefault(vid_hex, {"name": vendor_names.get(vid_hex), "products": {}})
        for pname, data in products.items():
            out["vendors"][vid_hex]["products"][pname] = {
                "pids": sorted(list(data["pids"])),
                "capabilities": sorted(list(data["capabilities"])),
            }

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    return out


def load_capabilities_json(path: str) -> Dict[str, dict]:
    """Load a capabilities JSON written by export_connected_capabilities_json."""

    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


class EasySwitchController:
    """Helper for Logitech Easy-Switch devices that support host switching."""

    SUPPORTED_DEVICES: Set[Tuple[int, int]] = {
        (mac_hid.LOGITECH_VENDOR_ID, 0xB020),  # MX Master 3/3S (BT)
        (mac_hid.LOGITECH_VENDOR_ID, 0xB019),  # MX Master 2S (BT)
        (mac_hid.LOGITECH_VENDOR_ID, 0xB023),  # MX Keys
        (mac_hid.LOGITECH_VENDOR_ID, 0xB35B),  # MX Keys Mini
    }

    def __init__(self, device: mac_hid.HIDDevice):
        self.device = device

    @classmethod
    def from_device(cls, device: mac_hid.HIDDevice) -> Optional["EasySwitchController"]:
        if (device.vendor_id, device.product_id) not in cls.SUPPORTED_DEVICES:
            return None
        return cls(device)

    def switch_slot(self, slot: int, *, dry_run: bool = False, device_index: Optional[int] = None):
        return mac_hid.easy_switch_select_host(self.device, slot, device_index=device_index, dry_run=dry_run)

    @property
    def product_id(self) -> int:
        return self.device.product_id

    @property
    def serial_number(self) -> Optional[str]:
        return self.device.serial_number


def easy_switch_controllers(devices: Optional[Iterable[mac_hid.HIDDevice]] = None) -> List[EasySwitchController]:
    """Return Easy-Switch controllers for the given devices (defaults to connected ones)."""

    if devices is None:
        devices = mac_hid.list_logitech_devices()
    result: List[EasySwitchController] = []
    for device in devices:
        controller = EasySwitchController.from_device(device)
        if controller:
            result.append(controller)
    return result


def switch_easy_switch_device(
    slot: int,
    *,
    product_id: Optional[int] = None,
    serial_number: Optional[str] = None,
    dry_run: bool = False,
    vendor_id: Optional[int] = mac_hid.LOGITECH_VENDOR_ID,
    device_index: Optional[int] = None,
) -> mac_hid.HIDDevice:
    """Switch the given Easy-Switch device to ``slot`` and return the matched device."""

    if slot not in (1, 2, 3):
        raise ValueError("Easy-Switch slot must be 1, 2, or 3")

    devices = mac_hid.list_hid_devices(vendor_id)
    controllers = easy_switch_controllers(devices)

    if product_id is not None:
        controllers = [c for c in controllers if c.product_id == product_id]
    if serial_number is not None:
        controllers = [c for c in controllers if c.serial_number == serial_number]

    if not controllers:
        raise ValueError("No Easy-Switch capable devices detected")
    if len(controllers) > 1 and product_id is None and serial_number is None:
        raise ValueError("Multiple Easy-Switch devices detected; specify --product-id or --serial")

    controller = controllers[0]
    controller.switch_slot(slot, dry_run=dry_run, device_index=device_index)
    return controller.device
