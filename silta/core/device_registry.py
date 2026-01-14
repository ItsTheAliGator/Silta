from typing import List, Dict, Optional
from dataclasses import dataclass
from silta.hid.enumeration import list_hid_devices, HIDDevice
from silta.hid import LOGITECH_VENDOR_ID

@dataclass
class InputStrategy:
    type: str  # 'hardware_direct' or 'software_relay'
    target_handle: Optional[object] = None # HIDDevice or None

@dataclass
class RegisteredDevice:
    id: str
    name: str
    kind: str # 'mouse', 'keyboard'
    strategy: InputStrategy
    hid_device: Optional[HIDDevice] = None

class DeviceRegistry:
    def __init__(self):
        self._devices: Dict[str, RegisteredDevice] = {}

    def scan_devices(self) -> List[RegisteredDevice]:
        """
        Scan for connected input devices and determine their optimal strategy.
        """
        self._devices.clear()
        
        # 1. Scan HID devices (Mice/Keyboards)
        hid_devs = list_hid_devices()
        for dev in hid_devs:
            # We only care about Mice/Keyboards generally
            # Usage Page 1, Usage 2 (Mouse) or 6 (Keyboard)
            if dev.usage_page == 1 and dev.usage in (2, 6):
                kind = 'mouse' if dev.usage == 2 else 'keyboard'
                
                # Check for Hardware Strategy (Logitech Easy-Switch)
                is_logitech = dev.vendor_id == LOGITECH_VENDOR_ID
                # TODO: Check specific PID capabilities via external data
                # For now assume if logitech mouse, it might be.
                # Real logic needs capabilities check.
                
                # Simplified strategy determination:
                if is_logitech and kind == 'mouse':
                    strategy = InputStrategy('hardware_direct', dev)
                else:
                    strategy = InputStrategy('software_relay')

                reg = RegisteredDevice(
                    id=f"{dev.vendor_id}:{dev.product_id}:{dev.location_id}",
                    name=dev.product or "Unknown Device",
                    kind=kind,
                    strategy=strategy,
                    hid_device=dev
                )
                self._devices[reg.id] = reg
        
        # 2. Add "Built-in" fallbacks if not detected?
        # Often built-in keyboard/trackpad shows up in IORegistry logic.
        
        return list(self._devices.values())

    def get_device(self, device_id: str) -> Optional[RegisteredDevice]:
        return self._devices.get(device_id)
