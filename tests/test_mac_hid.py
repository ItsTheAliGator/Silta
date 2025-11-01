import plistlib
import subprocess
import sys
from types import SimpleNamespace

import pytest

from silta import mac_hid


@pytest.fixture(autouse=True)
def force_darwin(monkeypatch):
    monkeypatch.setattr(mac_hid, "sys", SimpleNamespace(platform="darwin"))


def test_list_hid_devices_parses_entries(monkeypatch):
    sample = plistlib.dumps(
        [
            {
                "VendorID": "0x046D",
                "ProductID": "0xC52B",
                "Transport": "Bluetooth",
                "Manufacturer": "Logitech",
                "Product": "MX Keys",
                "SerialNumber": "1234",
                "LocationID": "0x123456",
            }
        ]
    )

    monkeypatch.setattr(mac_hid, "_run_ioreg", lambda: sample)

    devices = mac_hid.list_hid_devices()

    assert len(devices) == 1
    device = devices[0]
    assert device.vendor_id == 0x046D
    assert device.product_id == 0xC52B
    assert device.transport == "Bluetooth"
    assert device.product == "MX Keys"


def test_build_report_plist_roundtrip():
    payload = mac_hid.build_report_plist(0x10, b"\x01\x02", report_type="feature")
    parsed = plistlib.loads(payload)
    assert parsed["ReportID"] == 0x10
    assert parsed["ReportType"] == "feature"
    assert parsed["Report"]["Data"] == [1, 2]


def test_run_hidutil_report_invokes_subprocess(monkeypatch):
    calls = []

    def fake_run(args, capture_output, check, text):
        calls.append(args)

        class Result:
            stdout = ""
            stderr = ""
            returncode = 0

        return Result()

    monkeypatch.setattr(
        mac_hid,
        "subprocess",
        SimpleNamespace(run=fake_run, CalledProcessError=subprocess.CalledProcessError),
    )

    match = {"VendorID": 0x046D, "ProductID": 0xC52B}
    report = mac_hid.build_report_plist(0x10, b"\x00")

    mac_hid.run_hidutil_report(match, report)

    assert calls
    cmd = calls[0]
    assert cmd[0] == "/usr/bin/hidutil"
    assert cmd[1] == "report"


def test_build_hidpp_short_command_padding():
    payload = mac_hid.build_hidpp_short_command(0x63, 0x01, (3,), device_index=0x02)
    assert payload == bytes([0x10, 0x02, 0x63, 0x01, 0x03, 0x00, 0x00])


def test_easy_switch_select_host_dry_run(monkeypatch):
    device = mac_hid.HIDDevice(
        vendor_id=mac_hid.LOGITECH_VENDOR_ID,
        product_id=0xB020,
        transport="Bluetooth",
        manufacturer="Logitech",
        product="MX Master 3",
        serial_number="ABC",
        location_id=None,
    )

    result = mac_hid.easy_switch_select_host(device, 2, dry_run=True)
    payload = result["payload"]
    assert payload == bytes([0x10, 0x02, 0x63, 0x01, 0x02, 0x00, 0x00])
    assert result["matching"]["ProductID"] == device.product_id
    assert result["method"] == "hidutil"

    with pytest.raises(ValueError):
        mac_hid.easy_switch_select_host(device, 5, dry_run=True)


def test_easy_switch_select_host_executes(monkeypatch):
    device = mac_hid.HIDDevice(
        vendor_id=mac_hid.LOGITECH_VENDOR_ID,
        product_id=0xB020,
        transport="USB",
        manufacturer="Logitech",
        product="MX Master 3",
        serial_number="DEF",
        location_id=None,
    )

    calls = {}

    def fake_run(match, report):
        calls["matching"] = plistlib.loads(plistlib.dumps(match))
        calls["report"] = plistlib.loads(report)

    monkeypatch.setattr(mac_hid, "run_hidutil_report", fake_run)

    mac_hid.easy_switch_select_host(device, 1, dry_run=False)
    assert calls["matching"]["ProductID"] == device.product_id
    data = calls["report"]["Report"]["Data"]
    assert data[:5] == [0x10, 0x01, 0x63, 0x01, 0x01]


def test_easy_switch_select_host_fallbacks_to_hidapi(monkeypatch):
    device = mac_hid.HIDDevice(
        vendor_id=mac_hid.LOGITECH_VENDOR_ID,
        product_id=0xB020,
        transport="Bluetooth",
        manufacturer="Logitech",
        product="MX Master 3",
        serial_number="SERIAL",
        location_id=None,
    )

    def fake_hidutil(*_args, **_kwargs):
        raise RuntimeError("Unknown command: report")

    monkeypatch.setattr(mac_hid, "run_hidutil_report", fake_hidutil)

    class FakeDevice:
        def __init__(self, path=None, **_kwargs):
            assert path == "devpath"
            self.closed = False

        def send_feature_report(self, data):
            self.data = data
            return len(data)

        def close(self):
            self.closed = True

    fake_hid = SimpleNamespace(
        enumerate=lambda vid, pid: [{"path": "devpath", "serial_number": "SERIAL"}],
        Device=FakeDevice,
    )

    monkeypatch.setitem(sys.modules, "hid", fake_hid)

    result = mac_hid.easy_switch_select_host(device, 3)
    assert result["method"] == "hidapi"
    assert result["bytes_written"] == 7


def test_easy_switch_select_host_iokit_fallback(monkeypatch):
    device = mac_hid.HIDDevice(
        vendor_id=mac_hid.LOGITECH_VENDOR_ID,
        product_id=0xB020,
        transport="Bluetooth",
        manufacturer="Logitech",
        product="MX Master 3",
        serial_number="SERIAL",
        location_id=None,
    )

    def fake_hidutil(*_args, **_kwargs):
        raise RuntimeError("Unknown command: report")

    monkeypatch.setattr(mac_hid, "run_hidutil_report", fake_hidutil)
    monkeypatch.setattr(mac_hid, "_easy_switch_via_hidapi", lambda *_: (_ for _ in ()).throw(RuntimeError("hidapi fail")))
    monkeypatch.setattr(mac_hid, "_easy_switch_via_hidapi_output", lambda *_: (_ for _ in ()).throw(RuntimeError("hidapi output fail")))

    expected = {"method": "iokit-ble", "bytes_written": 20}

    def fake_iokit(device_arg, slot):
        assert device_arg is device
        assert slot == 2
        return expected

    monkeypatch.setattr(mac_hid, "_easy_switch_via_iokit_ble", fake_iokit)

    result = mac_hid.easy_switch_select_host(device, 2)
    assert result == expected


def test_easy_switch_select_host_all_backends_fail(monkeypatch):
    device = mac_hid.HIDDevice(
        vendor_id=mac_hid.LOGITECH_VENDOR_ID,
        product_id=0xB020,
        transport="Bluetooth",
        manufacturer="Logitech",
        product="MX Master 3",
        serial_number=None,
        location_id=None,
    )

    def fail(*_args, **_kwargs):
        raise RuntimeError("fail")

    def raise_runtime_error(*args, **kwargs):
        raise RuntimeError("Unknown command: report")
    monkeypatch.setattr(mac_hid, "run_hidutil_report", raise_runtime_error)
    monkeypatch.setattr(mac_hid, "_easy_switch_via_hidapi", fail)
    monkeypatch.setattr(mac_hid, "_easy_switch_via_hidapi_output", fail)
    monkeypatch.setattr(mac_hid, "_easy_switch_via_iokit_ble", fail)

    with pytest.raises(RuntimeError) as excinfo:
        mac_hid.easy_switch_select_host(device, 1)
    assert "hidutil unsupported" in str(excinfo.value)
