import pytest

import flowlite.cursor as cursor


@pytest.fixture(autouse=True)
def reset_screen_cache(monkeypatch):
    monkeypatch.setattr(cursor, "_SCREEN_SIZE_CACHE", None, raising=False)


def test_probe_screen_size_prefers_first_valid(monkeypatch):
    monkeypatch.setattr(cursor, "_quartz_screen_size", lambda: None)
    monkeypatch.setattr(cursor, "_pyautogui_screen_size", lambda: (640, 480))
    monkeypatch.setattr(cursor, "_ctypes_screen_size", lambda: (800, 600))
    monkeypatch.setattr(cursor, "_tkinter_screen_size", lambda: (1024, 768))
    assert cursor._probe_screen_size() == (640, 480)


def test_probe_screen_size_falls_back(monkeypatch):
    monkeypatch.setattr(cursor, "_quartz_screen_size", lambda: None)
    monkeypatch.setattr(cursor, "_pyautogui_screen_size", lambda: None)
    monkeypatch.setattr(cursor, "_ctypes_screen_size", lambda: None)
    monkeypatch.setattr(cursor, "_tkinter_screen_size", lambda: None)
    assert cursor._probe_screen_size() == (1920, 1080)


def test_screen_size_caches_result(monkeypatch):
    calls = []

    def fake_pyautogui():
        calls.append(1)
        return (1280, 720)

    monkeypatch.setattr(cursor, "_quartz_screen_size", lambda: None)
    monkeypatch.setattr(cursor, "_pyautogui_screen_size", fake_pyautogui)
    monkeypatch.setattr(cursor, "_ctypes_screen_size", lambda: None)
    monkeypatch.setattr(cursor, "_tkinter_screen_size", lambda: None)

    assert cursor._screen_size() == (1280, 720)
    assert cursor._screen_size() == (1280, 720)
    assert len(calls) == 1
