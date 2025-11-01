import pytest

from silta.capabilities import (
    capabilities_for,
    summarize,
    EASY_SWITCH,
    EasySwitchController,
    easy_switch_controllers,
    switch_easy_switch_device,
)
from silta.mac_hid import HIDDevice, LOGITECH_VENDOR_ID


class Device:
    def __init__(self, vid, pid, transport=None, product=None):
        self.vendor_id = vid
        self.product_id = pid
        self.transport = transport
        self.product = product


def test_known_device_returns_capabilities():
    caps = capabilities_for(0x046D, 0xB023)  # MX Keys
    keys = [c.key for c in caps]
    assert "easy_switch" in keys


def test_unknown_device_has_no_caps():
    caps = capabilities_for(0x1234, 0x5678)
    assert caps == []


def test_summarize_includes_labels():
    dev = Device(0x046D, 0xB023, transport="Bluetooth", product="MX Keys")
    text = summarize(dev)
    assert "Easy" in text or "easy" in text


def _make_hid_device(pid, serial="ABC123"):
    return HIDDevice(
        vendor_id=LOGITECH_VENDOR_ID,
        product_id=pid,
        transport="Bluetooth",
        manufacturer="Logitech",
        product="MX Device",
        serial_number=serial,
        location_id=None,
    )


def test_easy_switch_controller_switch_slot(monkeypatch):
    device = _make_hid_device(0xB020)
    controller = EasySwitchController.from_device(device)
    assert controller is not None

    calls = {}

    def fake_switch(dev, slot, device_index=None, dry_run=False):
        calls.update({
            "device": dev,
            "slot": slot,
            "device_index": device_index,
            "dry_run": dry_run,
        })

    monkeypatch.setattr("silta.mac_hid.easy_switch_select_host", fake_switch)

    controller.switch_slot(2, dry_run=True, device_index=0x02)
    assert calls["device"] is device
    assert calls["slot"] == 2
    assert calls["device_index"] == 0x02
    assert calls["dry_run"] is True


def test_switch_easy_switch_device_filters(monkeypatch):
    dev1 = _make_hid_device(0xB020, serial="A")
    dev2 = _make_hid_device(0xB023, serial="B")

    monkeypatch.setattr("silta.mac_hid.list_hid_devices", lambda vendor_id=None: [dev1, dev2])

    captured = {}

    def fake_switch(dev, slot, device_index=None, dry_run=False):
        captured["device"] = dev
        captured["slot"] = slot
        captured["dry_run"] = dry_run

    monkeypatch.setattr("silta.mac_hid.easy_switch_select_host", fake_switch)

    chosen = switch_easy_switch_device(3, product_id=dev1.product_id, dry_run=True)
    assert chosen is dev1
    assert captured["slot"] == 3
    assert captured["dry_run"] is True

    with pytest.raises(ValueError):
        switch_easy_switch_device(1, vendor_id=LOGITECH_VENDOR_ID)


def test_easy_switch_controllers_enumeration(monkeypatch):
    dev = _make_hid_device(0xB020)
    monkeypatch.setattr("silta.mac_hid.list_logitech_devices", lambda: [dev])
    controllers = easy_switch_controllers()
    assert len(controllers) == 1
    assert controllers[0].device is dev
