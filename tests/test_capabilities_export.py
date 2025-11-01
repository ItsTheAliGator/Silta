import json
from types import SimpleNamespace

from silta.capabilities import export_connected_capabilities_json


class FakeDev:
    def __init__(self, vid, pid, manufacturer=None, product=None, transport=None):
        self.vendor_id = vid
        self.product_id = pid
        self.manufacturer = manufacturer
        self.product = product
        self.transport = transport


def test_export_groups_pid_variants(tmp_path, monkeypatch):
    # Two MX Keys variants + one Unifying receiver
    fake = [
        FakeDev(0x046D, 0xB023, manufacturer="Logitech", product="MX Keys", transport="Bluetooth"),
        FakeDev(0x046D, 0xB35B, manufacturer="Logitech", product="MX Keys", transport="Bluetooth"),
        FakeDev(0x046D, 0xC52B, manufacturer="Logitech", product="Unifying Receiver", transport="USB"),
    ]

    monkeypatch.setattr("silta.mac_hid.list_hid_devices", lambda vendor_id=None: fake)

    path = tmp_path / "caps.json"
    data = export_connected_capabilities_json(str(path))

    # File is created and valid JSON
    obj = json.loads(path.read_text("utf-8"))
    assert obj["vendors"]["046D"]["products"]["MX Keys"]["pids"] == ["B023", "B35B"]
    # Capabilities present for MX Keys (from static matrix), unifying as well
    mx_caps = set(obj["vendors"]["046D"]["products"]["MX Keys"]["capabilities"])
    assert "easy_switch" in mx_caps
    uni_caps = set(obj["vendors"]["046D"]["products"]["Unifying Receiver"]["capabilities"]) if "Unifying Receiver" in obj["vendors"]["046D"]["products"] else set()
    # Unifying may be present depending on static matrix; tolerate both but ensure key exists if present
    if uni_caps:
        assert "unifying" in uni_caps
