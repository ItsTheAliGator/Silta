import plistlib
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

    def fake_run(args, capture_output, check):
        calls.append(args)

        class Result:
            stdout = b""
            stderr = b""
            returncode = 0

        return Result()

    monkeypatch.setattr(mac_hid, "subprocess", SimpleNamespace(run=fake_run))

    match = {"VendorID": 0x046D, "ProductID": 0xC52B}
    report = mac_hid.build_report_plist(0x10, b"\x00")

    mac_hid.run_hidutil_report(match, report)

    assert calls
    cmd = calls[0]
    assert cmd[0] == "/usr/bin/hidutil"
    assert cmd[1] == "report"
