from __future__ import annotations

"""Minimal menubar UI to show host, displays, devices, and mouse speed.

MVP uses a status bar menu (simple, native). Later, we can switch to a popover
with NSVisualEffectView for a glass look.
"""

import socket
import os
from typing import List, Optional

import objc  # type: ignore
from Foundation import NSObject  # type: ignore

from .capabilities import capabilities_for, export_connected_capabilities_json
from .display_info import get_displays
from .mouse_prefs import read_mouse_speed
from silta.hid import list_hid_devices, easy_switch_select_host
from .utils import LOG


def _format_display_line(d) -> str:
    name = d.name or ("Internal Display" if d.is_builtin else f"Display {d.id}")
    size = f"{d.pixels_w}×{d.pixels_h}@{d.scale:.1f}x"
    if d.refresh_hz:
        hz = f"{d.refresh_hz:.0f}Hz"
    elif d.max_fps:
        hz = f"VRR up to {d.max_fps}Hz"
    else:
        hz = "—"
    flags = []
    if d.is_main:
        flags.append("main")
    if d.is_mirrored:
        flags.append("mirrored")
    if d.rotation:
        flags.append(f"rot {int(d.rotation)}°")
    suffix = f" ({', '.join(flags)})" if flags else ""
    return f"{name}: {size} {hz}{suffix}"


def _append_device(menu, AppKit, dev, controller=None) -> None:
    # Format title with device type emoji and internal/external indicator
    # Only focus on mice/keyboards; other device categories are not core to Silta
    device_type_emojis = {
        "mouse": "🖱️",
        "keyboard": "⌨️",
    }
    emoji = device_type_emojis.get(dev.device_type, "🔌")
    
    product_name = dev.product or f"VID {dev.vendor_id:04X} PID {dev.product_id:04X}"
    location = "(Internal)" if dev.is_builtin else "(External)"
    
    title = f"{emoji} {product_name} {location}"
    
    if dev.transport and not dev.is_builtin:
        title = f"{title} - {dev.transport}"
    
    item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
    submenu = AppKit.NSMenu.alloc().init()

    caps = capabilities_for(getattr(dev, "vendor_id", 0), getattr(dev, "product_id", 0))
    has_easy_switch = False
    if caps:
        for cap in caps:
            submenu.addItemWithTitle_action_keyEquivalent_(f"• {cap.label}", None, "")
            if "Easy-Switch" in cap.label:
                has_easy_switch = True
    else:
        submenu.addItemWithTitle_action_keyEquivalent_("No known special capabilities", None, "")

    # Add Easy-Switch test buttons if device supports it
    if has_easy_switch and controller:
        submenu.addItem_(AppKit.NSMenuItem.separatorItem())
        test_label = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Test Easy-Switch:", None, ""
        )
        test_label.setEnabled_(False)
        submenu.addItem_(test_label)
        
        for slot in range(1, 4):  # Slots 1, 2, 3
            slot_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                f"Switch to Slot {slot}", f"switchToSlot{slot}:", ""
            )
            slot_item.setTarget_(controller)
            submenu.addItem_(slot_item)

    details = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        f"VID 0x{dev.vendor_id:04X} PID 0x{dev.product_id:04X}",
        None,
        "",
    )
    details.setEnabled_(False)
    submenu.insertItem_atIndex_(details, 0)

    item.setSubmenu_(submenu)
    menu.addItem_(item)


def _default_capabilities_path() -> str:
    docs_dir = os.path.join(os.getcwd(), "docs")
    if os.path.isdir(docs_dir):
        return os.path.join(docs_dir, "capabilities.json")
    return os.path.join(os.getcwd(), "capabilities.json")


def _normalize_export_path(path_hint: Optional[str]) -> str:
    if not path_hint or path_hint == "__DEFAULT__":
        return _default_capabilities_path()
    expanded = os.path.expanduser(path_hint)
    if not os.path.isabs(expanded):
        expanded = os.path.abspath(expanded)
    return expanded


def _export_capabilities(path_hint: Optional[str]) -> str:
    path = _normalize_export_path(path_hint)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    export_connected_capabilities_json(path)
    return path


class _MenuController(NSObject):
    def initWithFeedbackItem_exportPath_devices_(self, feedback_item, export_path, devices):  # noqa: N802 - PyObjC signature
        self = objc.super(_MenuController, self).init()
        if self is None:
            return None
        self._feedback_item = feedback_item
        self._export_path = export_path
        self._devices = devices or []
        return self

    def exportCapabilities_(self, _sender):  # noqa: N802 - PyObjC action signature
        try:
            path = _export_capabilities(self._export_path)
            message = f"Capabilities exported to {path}"
        except OSError as exc:
            LOG.exception("Failed to export capabilities: %s", exc)
            message = f"Export failed: {exc}"
        if self._feedback_item is not None:
            self._feedback_item.setTitle_(message)

    def switchToSlot1_(self, _sender):  # noqa: N802 - PyObjC action signature
        self._switch_slot(1)

    def switchToSlot2_(self, _sender):  # noqa: N802 - PyObjC action signature
        self._switch_slot(2)

    def switchToSlot3_(self, _sender):  # noqa: N802 - PyObjC action signature
        self._switch_slot(3)

    def _switch_slot(self, slot: int) -> None:
        """Switch all Easy-Switch capable devices to the specified slot."""
        for dev in self._devices:
            caps = capabilities_for(getattr(dev, "vendor_id", 0), getattr(dev, "product_id", 0))
            if not caps:
                continue
            has_easy_switch = any("Easy-Switch" in cap.label for cap in caps)
            if not has_easy_switch:
                continue
            
            try:
                product_name = dev.product or f"VID {dev.vendor_id:04X} PID {dev.product_id:04X}"
                LOG.info(f"Switching {product_name} to slot {slot}")
                # Call Easy-Switch using the enumerated HIDDevice instance
                easy_switch_select_host(
                    device=dev,
                    slot=slot,
                    dry_run=False,
                )
                message = f"Switched {product_name} to slot {slot}"
                LOG.info(message)
                if self._feedback_item is not None:
                    self._feedback_item.setTitle_(message)
            except RuntimeError as exc:
                LOG.exception("Failed to switch %s to slot %d: %s", dev.product, slot, exc)
                error_msg = f"Switch failed: {exc}"
                if self._feedback_item is not None:
                    self._feedback_item.setTitle_(error_msg)

    def openConnectionManager_(self, _sender):  # noqa: N802 - PyObjC action signature
        """Open the Connection Manager window within the current app runloop."""
        try:
            # Import lazily to avoid heavy imports on menu creation
            from silta.gui import open_window_in_current_app
            # Ask connection_window to open a window without starting a new app loop
            open_window_in_current_app()
        except Exception as exc:
            LOG.exception("Failed to open Connection Manager window: %s", exc)
            if self._feedback_item is not None:
                self._feedback_item.setTitle_(f"Open window failed: {exc}")


_ACTIVE_CONTROLLERS: List[_MenuController] = []


def run(*, export_path: Optional[str] = None) -> None:  # pragma: no cover - UI
    try:
        import AppKit  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise SystemExit("PyObjC AppKit is required for the GUI (pip install pyobjc-framework-AppKit)") from exc

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    status_bar = AppKit.NSStatusBar.systemStatusBar()
    item = status_bar.statusItemWithLength_(AppKit.NSVariableStatusItemLength)
    item.button().setTitle_("Silta")

    menu = AppKit.NSMenu.alloc().init()

    feedback_message = "Capabilities JSON: not exported"
    if export_path is not None:
        try:
            export_dest = _export_capabilities(export_path)
            feedback_message = f"Capabilities exported to {export_dest}"
        except Exception as exc:  # noqa: BLE001
            LOG.exception("Failed to export capabilities on launch: %s", exc)
            feedback_message = f"Export failed: {exc}"

    # Hostname
    host = socket.gethostname()
    menu.addItemWithTitle_action_keyEquivalent_(f"Host: {host}", None, "")
    menu.addItem_(AppKit.NSMenuItem.separatorItem())

    # Displays
    try:
        displays = get_displays()
        if displays:
            menu.addItemWithTitle_action_keyEquivalent_("Displays:", None, "")
            for d in displays:
                menu.addItemWithTitle_action_keyEquivalent_(_format_display_line(d), None, "")
        else:
            menu.addItemWithTitle_action_keyEquivalent_("No displays detected", None, "")
    except Exception as exc:
        LOG.exception("Failed to enumerate displays: %s", exc)
        menu.addItemWithTitle_action_keyEquivalent_("Display info unavailable", None, "")

    menu.addItem_(AppKit.NSMenuItem.separatorItem())

    # Create controller early so we can pass it to device menu items
    feedback_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(feedback_message, None, "")
    feedback_item.setEnabled_(False)
    
    # Devices (read-only hints)
    devices = []
    try:
        devices = list_hid_devices()
    except Exception as exc:
        LOG.exception("Failed to enumerate HID devices: %s", exc)
    
    controller = _MenuController.alloc().initWithFeedbackItem_exportPath_devices_(feedback_item, export_path, devices)
    _ACTIVE_CONTROLLERS.append(controller)
    
    # Now add device menu items with controller attached (only mice/keyboards)
    if devices:
        # Group devices by type (ignore joysticks/gamepads/digitizers/touchscreens)
        mice = [d for d in devices if d.device_type == "mouse"]
        keyboards = [d for d in devices if d.device_type == "keyboard"]

        if mice:
            menu.addItemWithTitle_action_keyEquivalent_("🖱️  Mice:", None, "")
            for dev in mice:
                _append_device(menu, AppKit, dev, controller)

        if keyboards:
            if mice:  # Add separator if we had mice before
                menu.addItem_(AppKit.NSMenuItem.separatorItem())
            menu.addItemWithTitle_action_keyEquivalent_("⌨️  Keyboards:", None, "")
            for dev in keyboards:
                _append_device(menu, AppKit, dev, controller)
    else:
        menu.addItemWithTitle_action_keyEquivalent_("No HID devices found", None, "")

    menu.addItem_(AppKit.NSMenuItem.separatorItem())

    export_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Export capabilities JSON", "exportCapabilities:", ""
    )
    export_item.setTarget_(controller)
    menu.addItem_(export_item)

    # Open Connection Manager window
    open_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Open Connection Manager…", "openConnectionManager:", ""
    )
    open_item.setTarget_(controller)
    menu.addItem_(open_item)
    menu.addItem_(feedback_item)
    menu.addItem_(AppKit.NSMenuItem.separatorItem())

    # Mouse speed
    spd = read_mouse_speed()
    menu.addItemWithTitle_action_keyEquivalent_(
        f"Mouse speed: {spd:.2f}" if spd is not None else "Mouse speed: —",
        None,
        "",
    )

    menu.addItem_(AppKit.NSMenuItem.separatorItem())

    # Quit action
    def do_quit(_sender):  # noqa: ANN001
        AppKit.NSApp.terminate_(None)

    quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Quit", "terminate:", "q"
    )
    quit_item.setTarget_(app)
    menu.addItem_(quit_item)

    item.setMenu_(menu)
    app.run()
