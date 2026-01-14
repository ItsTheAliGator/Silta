from __future__ import annotations

from .base import StackTabBuilder, TabSetup, QuickAction
from silta.gui.views import _make_label
from silta.gui.views import _limit_width

class OverviewTabBuilder(StackTabBuilder):
    def _populate(self) -> TabSetup:
        AppKit = self._AppKit
        assert self._stack is not None
        stack = self._stack

        # --- Welcome Card ---
        card, body = self._cards.make_card(AppKit.NSMakeRect(0, 0, 500, 200), f"Welcome to Silta, {self._data.hostname()}")
        card.setTranslatesAutoresizingMaskIntoConstraints_(False)
        _limit_width(AppKit, card, 600.0)
        stack.addArrangedSubview_(card)

        # Body text
        lbl = _make_label(AppKit, "Move your mouse between computers seamlessly.", 13.0, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor())
        body.addSubview_(lbl)
        AppKit.NSLayoutConstraint.activateConstraints_([
            lbl.leadingAnchor().constraintEqualToAnchor_constant_(body.leadingAnchor(), 20.0),
            lbl.topAnchor().constraintEqualToAnchor_constant_(body.topAnchor(), 50.0),
            lbl.trailingAnchor().constraintEqualToAnchor_constant_(body.trailingAnchor(), -20.0),
        ])

        # --- Host Info ---
        host_stack = AppKit.NSStackView.stackViewWithViews_([])
        host_stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        host_stack.setSpacing_(16.0)
        host_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        
        ip_label = _make_label(AppKit, f"IP: {self._data.local_ip()}", 12.0, AppKit.NSFontWeightMedium, AppKit.NSColor.tertiaryLabelColor())
        host_stack.addArrangedSubview_(ip_label)
        
        body.addSubview_(host_stack)
        AppKit.NSLayoutConstraint.activateConstraints_([
            host_stack.leadingAnchor().constraintEqualToAnchor_constant_(body.leadingAnchor(), 20.0),
            host_stack.topAnchor().constraintEqualToAnchor_constant_(lbl.bottomAnchor(), 12.0),
        ])

        # --- Displays Card ---
        displays = self._data.connected_displays()
        display_card, display_body = self._cards.make_card(AppKit.NSMakeRect(0, 0, 500, 150), f"Displays ({len(displays)})")
        display_card.setTranslatesAutoresizingMaskIntoConstraints_(False)
        _limit_width(AppKit, display_card, 600.0)
        stack.addArrangedSubview_(display_card)

        display_stack = AppKit.NSStackView.stackViewWithViews_([])
        display_stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        display_stack.setSpacing_(8.0)
        display_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        display_body.addSubview_(display_stack)
        AppKit.NSLayoutConstraint.activateConstraints_([
            display_stack.leadingAnchor().constraintEqualToAnchor_constant_(display_body.leadingAnchor(), 20.0),
            display_stack.topAnchor().constraintEqualToAnchor_constant_(display_body.topAnchor(), 50.0),
            display_stack.bottomAnchor().constraintLessThanOrEqualToAnchor_constant_(display_body.bottomAnchor(), -20.0),
        ])

        if not displays:
            display_stack.addArrangedSubview_(_make_label(AppKit, "No displays detected", 13.0, AppKit.NSFontWeightRegular, AppKit.NSColor.tertiaryLabelColor()))
        else:
            for info in displays:
                row = AppKit.NSStackView.stackViewWithViews_([])
                row.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
                row.setAlignment_(AppKit.NSLayoutAttributeCenterY)
                row.setSpacing_(12.0)
                row.setTranslatesAutoresizingMaskIntoConstraints_(False)
                display_stack.addArrangedSubview_(row)

                icon = self._symbols.symbol(info.symbol, 18.0)
                icon_view = AppKit.NSImageView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 22, 22))
                icon_view.setTranslatesAutoresizingMaskIntoConstraints_(False)
                if icon is not None:
                    icon_view.setImage_(icon)
                    try:
                        icon_view.setContentTintColor_(AppKit.NSColor.secondaryLabelColor())
                    except Exception:  # noqa: BLE001
                        pass
                AppKit.NSLayoutConstraint.activateConstraints_([
                    icon_view.widthAnchor().constraintEqualToConstant_(22.0),
                    icon_view.heightAnchor().constraintEqualToConstant_(22.0),
                ])
                row.addArrangedSubview_(icon_view)
                row.addArrangedSubview_(_make_label(AppKit, info.title, 13.0, AppKit.NSFontWeightSemibold))
                row.addArrangedSubview_(_make_label(AppKit, info.subtitle, 12.0, AppKit.NSFontWeightRegular, AppKit.NSColor.tertiaryLabelColor()))

        actions = [
            QuickAction("pair", "Test Connection", "bolt.horizontal.circle"),
            QuickAction("reveal-profile", "Reveal Profile", "folder"),
            QuickAction("open-logs", "Open Logs", "doc.text.magnifyingglass"),
        ]
        handlers = [
            lambda: self._coordinator.present_pairing_sheet(),
            lambda: self._coordinator.reveal_profile(),
            lambda: self._coordinator.open_logs_directory(),
        ]
        return TabSetup(actions=actions, handlers=handlers)
