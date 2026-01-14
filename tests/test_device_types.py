"""Tests for HID device type detection and internal device identification."""

import pytest
from silta.mac_hid import HIDDevice


def test_device_type_mouse():
    """Test mouse detection (usage_page=0x01, usage=0x02)."""
    device = HIDDevice(
        vendor_id=0x046D,
        product_id=0xB023,
        transport="Bluetooth",
        manufacturer="Logitech",
        product="MX Master 3",
        serial_number="ABC123",
        location_id=None,
        usage_page=0x01,  # Generic Desktop
        usage=0x02,  # Mouse
    )
    assert device.device_type == "mouse"


def test_device_type_keyboard():
    """Test keyboard detection (usage_page=0x01, usage=0x06)."""
    device = HIDDevice(
        vendor_id=0x046D,
        product_id=0xB35B,
        transport="Bluetooth",
        manufacturer="Logitech",
        product="MX Keys Mini",
        serial_number="DEF456",
        location_id=None,
        usage_page=0x01,  # Generic Desktop
        usage=0x06,  # Keyboard
    )
    assert device.device_type == "keyboard"


def test_device_type_joystick():
    """Test joystick detection (usage_page=0x01, usage=0x04)."""
    device = HIDDevice(
        vendor_id=0x1234,
        product_id=0x5678,
        transport="USB",
        manufacturer="Generic",
        product="Joystick",
        serial_number=None,
        location_id=None,
        usage_page=0x01,
        usage=0x04,  # Joystick
    )
    assert device.device_type == "joystick"


def test_device_type_gamepad():
    """Test gamepad detection (usage_page=0x01, usage=0x05)."""
    device = HIDDevice(
        vendor_id=0x1234,
        product_id=0x5678,
        transport="USB",
        manufacturer="Generic",
        product="Gamepad",
        serial_number=None,
        location_id=None,
        usage_page=0x01,
        usage=0x05,  # Game Pad
    )
    assert device.device_type == "gamepad"


def test_device_type_consumer_remote():
    """Test remote control detection (usage_page=0x0C)."""
    device = HIDDevice(
        vendor_id=0x1234,
        product_id=0x5678,
        transport="USB",
        manufacturer="Generic",
        product="Remote",
        serial_number=None,
        location_id=None,
        usage_page=0x0C,  # Consumer
        usage=0x01,
    )
    assert device.device_type == "remote"


def test_device_type_unknown():
    """Test unknown device type."""
    device = HIDDevice(
        vendor_id=0x1234,
        product_id=0x5678,
        transport="USB",
        manufacturer="Generic",
        product="Unknown",
        serial_number=None,
        location_id=None,
        usage_page=0xFF,  # Vendor-specific
        usage=0xFF,
    )
    assert device.device_type == "unknown"


def test_device_type_none_usage():
    """Test device with no usage page/usage info."""
    device = HIDDevice(
        vendor_id=0x1234,
        product_id=0x5678,
        transport="USB",
        manufacturer="Generic",
        product="Device",
        serial_number=None,
        location_id=None,
        usage_page=None,
        usage=None,
    )
    assert device.device_type == "unknown"


def test_is_builtin_explicit_flag():
    """Test internal device detection via explicit built flag."""
    device = HIDDevice(
        vendor_id=0x05AC,  # Apple
        product_id=0x0273,
        transport="Internal",
        manufacturer="Apple",
        product="Apple Internal Keyboard",
        serial_number=None,
        location_id=None,
        built=True,  # Explicit flag
    )
    assert device.is_builtin is True


def test_is_builtin_apple_internal_pid():
    """Test internal device detection via known Apple PID."""
    device = HIDDevice(
        vendor_id=0x05AC,  # Apple
        product_id=0x0273,  # Known internal PID
        transport="USB",
        manufacturer="Apple",
        product="Keyboard",
        serial_number=None,
        location_id=None,
    )
    assert device.is_builtin is True


def test_is_builtin_location_id_pattern():
    """Test internal device detection via LocationID pattern."""
    device = HIDDevice(
        vendor_id=0x05AC,
        product_id=0x1234,
        transport="USB",
        manufacturer="Apple",
        product="Keyboard",
        serial_number=None,
        location_id=0x14100000,  # Within internal range
    )
    assert device.is_builtin is True


def test_is_builtin_product_name():
    """Test internal device detection via product name containing 'Internal'."""
    device = HIDDevice(
        vendor_id=0x05AC,
        product_id=0x1234,
        transport="USB",
        manufacturer="Apple",
        product="Apple Internal Keyboard / Trackpad",
        serial_number=None,
        location_id=None,
    )
    assert device.is_builtin is True


def test_is_builtin_transport_hint():
    """Test internal device detection via Transport field."""
    device = HIDDevice(
        vendor_id=0x05AC,
        product_id=0x1234,
        transport="Internal",
        manufacturer="Apple",
        product="Keyboard",
        serial_number=None,
        location_id=None,
    )
    assert device.is_builtin is True


def test_is_not_builtin_external_logitech():
    """Test that external Logitech devices are NOT marked as internal."""
    device = HIDDevice(
        vendor_id=0x046D,  # Logitech
        product_id=0xB023,
        transport="Bluetooth",
        manufacturer="Logitech",
        product="MX Master 3",
        serial_number="ABC123",
        location_id=0x02100000,  # External-like location
    )
    assert device.is_builtin is False


def test_is_not_builtin_no_indicators():
    """Test that devices with no internal indicators are marked as external."""
    device = HIDDevice(
        vendor_id=0x1234,
        product_id=0x5678,
        transport="USB",
        manufacturer="Generic",
        product="Mouse",
        serial_number=None,
        location_id=0x00100000,
    )
    assert device.is_builtin is False


def test_combined_mouse_and_builtin():
    """Test device that is both a mouse and potentially internal (shouldn't happen in practice)."""
    device = HIDDevice(
        vendor_id=0x05AC,
        product_id=0x0273,
        transport="Internal",
        manufacturer="Apple",
        product="Apple Internal Keyboard / Trackpad",
        serial_number=None,
        location_id=None,
        usage_page=0x01,
        usage=0x02,  # Mouse (for trackpad)
        built=True,
    )
    assert device.device_type == "mouse"
    assert device.is_builtin is True
