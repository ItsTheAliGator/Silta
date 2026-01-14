from __future__ import annotations

import collections
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from silta.hid import list_hid_devices, HIDDevice
from silta.utils import LOG

@dataclass
class DeviceRow:
    name: str
    subtitle: str
    device_type: str  # "mouse" or "keyboard" or "unknown"
    detail_chips: List[str] = field(default_factory=list)
    hid_device: Optional[HIDDevice] = None

@dataclass
class DeviceSection:
    heading: str
    rows: List[DeviceRow] = field(default_factory=list)

@dataclass
class DisplayRow:
    title: str
    subtitle: str
    symbol: str

class WindowDataProvider:
    def __init__(self) -> None:
        pass

    def hostname(self) -> str:
        return socket.gethostname().replace(".local", "")

    def profile_path(self) -> str:
        # Default internal path
        return str(Path.home() / "silta.json")

    def local_ip(self) -> str:
        try:
            # dummy connection to determine source IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    def connected_displays(self) -> List[DisplayRow]:
        # Uses Quartz to get display info (mocking logic if we don't assume external dependency for now,
        # but connection_window.py used Quartz.CGGetActiveDisplayList etc.)
        # We should port that logic.
        
        # Original logic was inline in connection_window or menubar.
        # Let's use a simplified version or the real one if we import Quartz.
        rows = []
        try:
            import Quartz  # type: ignore
            max_displays = 16
            active_displays = Quartz.CGGetActiveDisplayList(max_displays, None, None)
            if active_displays and active_displays[0]:
                displays = active_displays[1]
                for i, display_id in enumerate(displays):
                    width = Quartz.CGDisplayPixelsWide(display_id)
                    height = Quartz.CGDisplayPixelsHigh(display_id)
                    main = Quartz.CGDisplayIsMain(display_id)
                    title = f"Display {i + 1}"
                    if main:
                        title += " (Main)"
                    rows.append(DisplayRow(title, f"{width} × {height}", "display"))
        except ImportError:
            pass
        except Exception as exc:
            LOG.debug("Failed to list displays: %s", exc)
        return rows

    def device_sections(self) -> List[DeviceSection]:
        devices = list_hid_devices()
        mice_rows = []
        kb_rows = []
        
        for dev in devices:
            dtype = dev.device_type
            if dtype not in ("mouse", "keyboard"):
                continue
                
            name = dev.product or "Unknown Device"
            transport = dev.transport or "USB"
            if dev.is_builtin:
                transport = "Internal"
                
            chips = [transport]
            if dev.serial_number:
                # show short serial
                s = str(dev.serial_number)
                if len(s) > 8:
                    s = s[:4] + "..." + s[-4:]
                chips.append(f"S/N: {s}")
            
            row = DeviceRow(
                name=name,
                subtitle=f"VID 0x{dev.vendor_id:04X} PID 0x{dev.product_id:04X}",
                device_type=dtype,
                detail_chips=chips,
                hid_device=dev
            )
            
            if dtype == "mouse":
                mice_rows.append(row)
            else:
                kb_rows.append(row)
                
        sections = []
        if mice_rows:
            sections.append(DeviceSection("Mice", mice_rows))
        if kb_rows:
            sections.append(DeviceSection("Keyboards", kb_rows))
            
        return sections
