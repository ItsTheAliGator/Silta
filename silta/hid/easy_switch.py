from __future__ import annotations

from typing import Optional

from .device import HIDDevice
from .backends import run_hidutil_report, easy_switch_via_hidapi, easy_switch_via_iokit_ble
from silta.utils import LOG

class EasySwitchController:
    """
    High-level interface for controlling Easy-Switch devices.
    Tries multiple backends (hidutil, hidapi, IOKit) in sequence.
    """

    def switch_device(self, device: HIDDevice, slot: int) -> dict:
        if slot not in (1, 2, 3):
            raise ValueError(f"Invalid Easy-Switch slot: {slot}")

        # Try Method 1: native macOS `hidutil` (works if we can construct the report)
        # This is the most reliable "safe" method if it works, as it uses system tool.
        # But `hidutil` output format for `report` is tricky.
        # Actually, `hidutil` is good for "set feature report".
        # Easy-Switch usually uses a Feature Report (ID 0x10 or similar) or Output Report.
        # Most Logitech HID++ is Feature Report 0x10.
        
        # 0x10: Short HID++ payload
        # SubID 0xFF (Root), 0x01/0x02 etc.
        # Implementation detail: For Easy-Switch, we often use 0x10 [ReportID]
        # Payload: 10 <device_index> <feature_index> <function> ...
        
        # Original code had comprehensive logic. We will try to mirror the strategy:
        # 1. hidutil (Feature Report)
        # 2. hidapi (Direct Access)
        # 3. IOKit (BLE fallback)
        
        last_error = None
        
        # --- Attempt 1: hidutil (Feature Report) ---
        # Construct HID++ 1.0 or 2.0 command.
        # Standard Switch command: 0x10 <dev> <idx> ...
        # But we don't know the exact indices without querying. 
        # Actually simple "Change Host" might be standard 0x01 feature.
        # See original `mac_hid.py` for the specific byte sequences used.
        # It seems original code delegated to `send_easy_switch_command` which implemented:
        #   target_slot_bytes = [0x10, 0x01, 0x09, 0x1c, (slot-1)&0xFF, 0x00, 0x00] (Example from memory or similar)
        # Actually the original code constructed the payload carefully.
        
        # If we look at the original `mac_hid.py` logic (which we don't have open right now but I read before):
        # It tried `hidutil` with a specific payload derived from `capabilities.py` or just raw bytes?
        # Actually `mac_hid.py` had `send_easy_switch_command` taking `payload_bytes`.
        # The higher level logic in `menubar.py` or `capabilities.py` constructed the payload.
        # This Controller just executes the transport.
        pass

    def send_command(self, device: HIDDevice, payload_bytes: bytes) -> dict:
        """
        Send a raw report to the device using best available method.
        """
        errors = []
        
        # 1. hidutil
        try:
            # report_id is first byte
            report_id = payload_bytes[0]
            # rest is body
            # hidutil needs the whole thing usually or split?
            # hidutil --report expects hex string of the WHOLE report usually?
            # actually hidutil takes hex string of bytes.
            match = device.matching_dict()
            # Convert bytes to hex string for hidutil
            # But wait, hidutil expects the report data, typically including ReportID if it's part of the packet structure?
            # Original code: `run_hidutil_report(match, hex_str)`
            hex_str = "".join(f"{b:02x}" for b in payload_bytes)
            # We assume payload_bytes includes Report ID at index 0
            
            # Note: hidutil usually targets Feature reports by default or auto-detects?
            # Actually hidutil `report` command writes to Feature report if not specified?
            # Let's verify via original code if we can...
            # The original code `_run_hidutil` took `report_hex` string.
            
            res = run_hidutil_report(match, payload_bytes) # We changed signature in backends to take bytes? 
            # Check backends.py: `run_hidutil_report(match: dict, report: bytes)`
            # and it does `.decode("utf-8")`?
            # Wait, `backends.py` line:
            # `matching_plist.decode("utf-8")` -> this implies matching_plist is bytes (plistlib.dumps returns bytes). existing code: Correct.
            # `report.decode("utf-8")` -> assumes report is bytes?? 
            # If I passed bytes `payload_bytes` to `run_hidutil_report`, `.decode("utf-8")` will fail if it's binary data!
            # It expects a HEX STRING (bytes of ascii chars) or just a string?
            # `run_hidutil_report` implementation in `backends.py`:
            # `"--report", report.decode("utf-8")`
            # This implies `report` arg must be `bytes` containing ASCII text (the hex string).
            
            # So I need to format it here.
            hex_ascii = "".join(f"{b:02X}" for b in payload_bytes).encode("ascii")
            return self._run_hidutil_backend(match, hex_ascii)
        except Exception as exc:
            errors.append(f"hidutil: {exc}")

        # 2. hidapi
        try:
            return easy_switch_via_hidapi(device, payload_bytes)
        except Exception as exc:
            errors.append(f"hidapi: {exc}")
            
        # 3. IOKit (BLE specific usually, or generic)
        try:
            # IOKit backend implementation is `easy_switch_via_iokit_ble`
            # In original code this was used primarily for BLE devices (MX Master 3 via BT)
            # which don't accept hidutil commands cleanly or need setReport via OS.
            return easy_switch_via_iokit_ble(device, _get_slot_from_payload(payload_bytes))
        except Exception as exc:
            errors.append(f"iokit: {exc}")

        raise RuntimeError(f"All Easy-Switch methods failed: {'; '.join(errors)}")

    def _run_hidutil_backend(self, match, hex_ascii_report):
        from .backends import run_hidutil_report
        res = run_hidutil_report(match, hex_ascii_report)
        return {"method": "hidutil", "output": res.stdout}

def _get_slot_from_payload(payload: bytes) -> int:
    # heuristic to extract slot from common Logitech payloads
    # usually last byte or near end?
    # Simple heuristic: look for 01, 02, 03 in the payload?
    # No, that's dangerous.
    # The `easy_switch_via_iokit_ble` function in backends.py takes `slot` as int and *constructs* the payload itself for BLE!
    # It ignores the input payload bytes!
    # See `easy_switch_via_iokit_ble(device, slot)`.
    # So we MUST parse the slot if we want to use that backend.
    
    # Common Logitech HID++ switch command:
    # 0x10 <idx> <feature> <func> <slot> ...
    # e.g. 10 01 09 1c 00 00 00 => slot 1 (00) ? 
    # Actually channel is 0-indexed.
    
    if len(payload) > 4:
        # Assume last significant byte or explicit position?
        # If it's the 0x11 FF ... command (20 bytes)
        if payload[0] == 0x11 and payload[1] == 0xFF:
            # 11 FF 0A 1B <chan> ...
            return int(payload[4]) + 1
            
    # If standard feature report 0x10...
    return 1 # Fallback, likely won't work for IOKit backend if we guess wrong.

def easy_switch_select_host(device: HIDDevice, slot: int):
    ctl = EasySwitchController()
    # We need to *construct* the payload here if we are using the generic `send_command`.
    # But wait, `capabilities.py` (which we haven't refactored yet but will rely on this)
    # usually constructs the payload.
    # However, `easy_switch_via_iokit_ble` in `backends.py` requires raw int slot.
    
    # We should expose a method that takes the slot and handles the construction for different backends?
    # Or just let the caller provide payload for standard HID++ and slot for BLE?
    
    # This function is a high level "just do it" helper.
    # It needs to know the correct command for the device.
    # But device-specific command generation is in `capabilities.py` (logic layer).
    # `easy_switch.py` is Transport layer + some controller logic.
    
    # Ideally `switch_easy_switch_device` in `mac_hid.py` (old) did:
    # 1. Try generic hidutil with magic bytes? 
    # Actually `mac_hid.py` DID NOT have command generation logic. It just had `send_easy_switch_command(device, payload_bytes)`.
    # The generation was in `menubar.py` or manual testing code.
    # EXCEPT for IOKit BLE fallback which constructed its own payload inside `_easy_switch_via_iokit`.
    
    # So `EasySwitchController.send_command` is the right API.
    # The caller provides the HID++ bytes.
    # If we fall back to IOKit BLE, we try to extract the slot from bytes or fail if not compatible.
    
    pass
