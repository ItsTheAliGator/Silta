from __future__ import annotations

from .base import StackTabBuilder, TabSetup, QuickAction
from silta.gui.views import _make_label, _make_chip, _limit_width
from silta.gui.data import DeviceRow

def create_placeholder_image_nsimage(AppKit, device_type: str, size: tuple[int, int]) -> object:
    # Minimal placeholder
    img = AppKit.NSImage.alloc().initWithSize_(size)
    img.lockFocus()
    AppKit.NSColor.lightGrayColor().set()
    AppKit.NSBezierPath.bezierPathWithOvalInRect_(AppKit.NSMakeRect(0, 0, size[0], size[1])).fill()
    img.unlockFocus()
    return img

class DevicesTabBuilder(StackTabBuilder):
    def _populate(self) -> TabSetup:
        AppKit = self._AppKit
        assert self._stack is not None
        stack = self._stack

        sections = self._data.device_sections()
        if not sections:
            stack.addArrangedSubview_(_make_label(AppKit, "No devices detected", 14.0, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor()))
        else:
            columns = AppKit.NSStackView.stackViewWithViews_([])
            columns.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
            columns.setSpacing_(24.0)
            columns.setAlignment_(AppKit.NSLayoutAttributeTop)
            columns.setTranslatesAutoresizingMaskIntoConstraints_(False)
            stack.addArrangedSubview_(columns)

            for section in sections:
                card, body = self._cards.make_card(AppKit.NSMakeRect(0, 0, 360, 400), section.heading)
                card.setTranslatesAutoresizingMaskIntoConstraints_(False)
                _limit_width(AppKit, card, 420.0)
                columns.addArrangedSubview_(card)

                section_stack = AppKit.NSStackView.stackViewWithViews_([])
                section_stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
                section_stack.setSpacing_(12.0)
                section_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
                body.addSubview_(section_stack)
                AppKit.NSLayoutConstraint.activateConstraints_([
                    section_stack.leadingAnchor().constraintEqualToAnchor_constant_(body.leadingAnchor(), 24.0),
                    section_stack.trailingAnchor().constraintEqualToAnchor_constant_(body.trailingAnchor(), -24.0),
                    section_stack.topAnchor().constraintEqualToAnchor_constant_(body.topAnchor(), 20.0),
                    section_stack.bottomAnchor().constraintLessThanOrEqualToAnchor_constant_(body.bottomAnchor(), -20.0),
                ])

                for device in section.rows:
                    section_stack.addArrangedSubview_(self._make_device_row(device))

        actions = [
            QuickAction("refresh-devices", "Refresh Devices", "arrow.clockwise"),
            QuickAction("open-bluetooth", "Bluetooth Settings", "dot.radiowaves.up.forward"),
            QuickAction("export-devices", "Export List", "square.and.arrow.up"),
        ]
        handlers = [
            lambda: self._coordinator.refresh_devices_tab(),
            lambda: self._coordinator.open_bluetooth_preferences(),
            lambda: self._coordinator.export_devices_report(),
        ]
        return TabSetup(actions=actions, handlers=handlers)

    def _make_device_row(self, device: DeviceRow) -> object:
        AppKit = self._AppKit
        row = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 100, 72))
        row.setTranslatesAutoresizingMaskIntoConstraints_(False)
        row.setWantsLayer_(True)
        layer = row.layer()
        if layer is not None:
            layer.setCornerRadius_(14.0)
            layer.setBackgroundColor_(AppKit.NSColor.windowBackgroundColor().colorWithAlphaComponent_(0.35).CGColor())

        row_stack = AppKit.NSStackView.stackViewWithViews_([])
        row_stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        row_stack.setAlignment_(AppKit.NSLayoutAttributeCenterY)
        row_stack.setSpacing_(14.0)
        row_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        row.addSubview_(row_stack)
        AppKit.NSLayoutConstraint.activateConstraints_([
            row_stack.leadingAnchor().constraintEqualToAnchor_constant_(row.leadingAnchor(), 16.0),
            row_stack.trailingAnchor().constraintEqualToAnchor_constant_(row.trailingAnchor(), -16.0),
            row_stack.topAnchor().constraintEqualToAnchor_constant_(row.topAnchor(), 12.0),
            row_stack.bottomAnchor().constraintEqualToAnchor_constant_(row.bottomAnchor(), -12.0),
        ])

        icon_view = AppKit.NSImageView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 40, 40))
        icon_view.setTranslatesAutoresizingMaskIntoConstraints_(False)
        symbol_name = {
            "mouse": "computermouse.fill",
            "keyboard": "keyboard.fill",
        }.get(device.device_type, "questionmark.circle")
        image = self._symbols.symbol(symbol_name, 26.0)
        if image is not None:
            icon_view.setImage_(image)
            try:
                icon_view.setContentTintColor_(AppKit.NSColor.secondaryLabelColor())
            except Exception:  # noqa: BLE001
                pass
        else:
            placeholder = create_placeholder_image_nsimage(AppKit, device.device_type, (40, 40))
            if placeholder:
                icon_view.setImage_(placeholder)
        AppKit.NSLayoutConstraint.activateConstraints_([
            icon_view.widthAnchor().constraintEqualToConstant_(40.0),
            icon_view.heightAnchor().constraintEqualToConstant_(40.0),
        ])
        row_stack.addArrangedSubview_(icon_view)

        text_stack = AppKit.NSStackView.stackViewWithViews_([])
        text_stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        text_stack.setSpacing_(4.0)
        text_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        row_stack.addArrangedSubview_(text_stack)
        text_stack.addArrangedSubview_(_make_label(AppKit, device.name, 14.0, AppKit.NSFontWeightSemibold))
        text_stack.addArrangedSubview_(_make_label(AppKit, device.subtitle, 11.0, AppKit.NSFontWeightRegular, AppKit.NSColor.tertiaryLabelColor()))

        chips_stack = AppKit.NSStackView.stackViewWithViews_([])
        chips_stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        chips_stack.setSpacing_(6.0)
        chips_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        text_stack.addArrangedSubview_(chips_stack)
        for chip_text in device.detail_chips:
            chips_stack.addArrangedSubview_(_make_chip(AppKit, chip_text))

        return row
