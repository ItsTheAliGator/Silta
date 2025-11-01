from silta.client import FlowClient


def test_normalize_hotkey_aliases() -> None:
    client = FlowClient.__new__(FlowClient)
    assert client._normalize_hotkey("<Option>+<Command>+F") == "<alt>+<cmd>+F"
    assert client._normalize_hotkey("<Win>+<Ctl>+D") == "<cmd>+<ctrl>+D"
