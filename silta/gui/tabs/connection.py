from __future__ import annotations

from .base import StackTabBuilder, TabSetup, QuickAction
from silta.gui.views import _make_body_text, _limit_width

class ConnectionTabBuilder(StackTabBuilder):
    def _populate(self) -> TabSetup:
        AppKit = self._AppKit
        assert self._stack is not None
        stack = self._stack

        card, body = self._cards.make_card(AppKit.NSMakeRect(0, 0, 720, 320), "Connection")
        card.setTranslatesAutoresizingMaskIntoConstraints_(False)
        _limit_width(AppKit, card, 860.0)
        stack.addArrangedSubview_(card)

        content_stack = AppKit.NSStackView.stackViewWithViews_([])
        content_stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        content_stack.setSpacing_(12.0)
        content_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        body.addSubview_(content_stack)
        AppKit.NSLayoutConstraint.activateConstraints_([
            content_stack.leadingAnchor().constraintEqualToAnchor_constant_(body.leadingAnchor(), 24.0),
            content_stack.trailingAnchor().constraintEqualToAnchor_constant_(body.trailingAnchor(), -24.0),
            content_stack.topAnchor().constraintEqualToAnchor_constant_(body.topAnchor(), 20.0),
            content_stack.bottomAnchor().constraintLessThanOrEqualToAnchor_constant_(body.bottomAnchor(), -20.0),
        ])

        content_stack.addArrangedSubview_(_make_body_text(AppKit, "Create or update an edge profile and validate connectivity."))
        path_label = _make_body_text(AppKit, f"Profile file: {self._data.profile_path()}", 11.0, AppKit.NSColor.tertiaryLabelColor())
        try:
            path_label.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(11.0, AppKit.NSFontWeightRegular))
        except Exception:  # noqa: BLE001
            pass
        content_stack.addArrangedSubview_(path_label)

        button_row = AppKit.NSStackView.stackViewWithViews_([])
        button_row.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        button_row.setAlignment_(AppKit.NSLayoutAttributeCenterY)
        button_row.setSpacing_(12.0)
        button_row.setTranslatesAutoresizingMaskIntoConstraints_(False)
        content_stack.addArrangedSubview_(button_row)

        primary_button = self._coordinator.create_button(
            "Pair with another PC…",
            lambda: self._coordinator.present_pairing_sheet(),
            symbol="bolt.horizontal.circle"
        )
        try:
            primary_button.setKeyEquivalent_("\r")
        except Exception:  # noqa: BLE001
            pass
        button_row.addArrangedSubview_(primary_button)

        reveal_button = self._coordinator.create_button(
            "Reveal Profile",
            lambda: self._coordinator.reveal_profile(),
            symbol="folder"
        )
        button_row.addArrangedSubview_(reveal_button)

        content_stack.addArrangedSubview_(_make_body_text(
            AppKit,
            "Tip: keep the Silta service running on your remote machine before pairing."
        ))

        actions = [
            QuickAction("pair-now", "Pair Now", "bolt.horizontal.circle"),
            QuickAction("reveal-profile", "Reveal Profile", "folder"),
            QuickAction("open-profiles", "Open Profiles Folder", "tray.full"),
        ]
        handlers = [
            lambda: self._coordinator.present_pairing_sheet(),
            lambda: self._coordinator.reveal_profile(),
            lambda: self._coordinator.open_profiles_directory(),
        ]
        return TabSetup(actions=actions, handlers=handlers)
