import json

import pytest

from flowlite.cli import load_edge_profile


def test_load_edge_profile_parses_entries(tmp_path):
    data = {
        "left": {"host": "192.168.0.2", "port": 60000},
        "default": {"host": "192.168.0.3", "auth_token": "secret"},
    }
    config_file = tmp_path / "profile.json"
    config_file.write_text(json.dumps(data), encoding="utf-8")

    profiles = load_edge_profile(str(config_file), 59873, None)

    assert profiles["left"] == ("192.168.0.2", 60000, None)
    assert profiles["default"] == ("192.168.0.3", 59873, "secret")


def test_load_edge_profile_rejects_invalid_entries(tmp_path):
    bad_edge = tmp_path / "bad.json"
    bad_edge.write_text(json.dumps({"diagonal": {"host": "x"}}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_edge_profile(str(bad_edge), 59873, None)

    missing_host = tmp_path / "missing.json"
    missing_host.write_text(json.dumps({"left": {"port": 1234}}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_edge_profile(str(missing_host), 59873, None)
