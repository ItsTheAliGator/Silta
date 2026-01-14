from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple, Sequence

def _make_label(AppKit, text: str, size: float, weight: float, color=None) -> object:
    label = AppKit.NSTextField.labelWithString_(text)
    label.setFont_(AppKit.NSFont.systemFontOfSize_weight_(size, weight))
    if color:
        label.setTextColor_(color)
    else:
        label.setTextColor_(AppKit.NSColor.labelColor())
    label.setTranslatesAutoresizingMaskIntoConstraints_(False)
    return label

def _make_chip(AppKit, text: str) -> object:
    chip = AppKit.NSTextField.labelWithString_(text)
    chip.setFont_(AppKit.NSFont.systemFontOfSize_weight_(10.0, AppKit.NSFontWeightMedium))
    chip.setTextColor_(AppKit.NSColor.secondaryLabelColor())
    chip.setBezeled_(True)
    chip.setBezelStyle_(AppKit.NSBezelStyleRounded)
    chip.setControlSize_(1)  # NSControlSizeSmall
    # Actually simple labelWithString doesn't support bezel style well.
    # Better to make a rounded layer backing or just text.
    # Reverting to simple text for stability based on original connection_window logic:
    # Original used: `chip.setBackgroundColor_(...)` on layer? 
    # Let's check original logic if needed. 
    # Original used: `_make_chip` returned a textField with some styling.
    # We'll use a simple styled label.
    chip.setDrawsBackground_(True)
    chip.setBackgroundColor_(AppKit.NSColor.quaternaryLabelColor())
    chip.setBordered_(False)
    # Add padding via layout or sizing?
    return chip

def _make_body_text(AppKit, text: str, size: float = 13.0, color=None) -> object:
    lbl = _make_label(AppKit, text, size, AppKit.NSFontWeightRegular, color)
    lbl.setSelectable_(True)
    return lbl

def _limit_width(AppKit, view, width: float) -> None:
    AppKit.NSLayoutConstraint.activateConstraints_([
        view.widthAnchor().constraintLessThanOrEqualToConstant_(width)
    ])

@dataclass
class QuickAction:
    action_id: str
    title: str
    symbol: str

class SymbolProvider:
    def __init__(self, AppKit) -> None:
        self.AppKit = AppKit
        self._cache = {}

    def symbol(self, name: str, point_size: float = 18.0) -> Optional[object]:
        key = (name, point_size)
        if key in self._cache:
            return self._cache[key]
        
        # Try SF Symbols
        image = self.AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
        if image is None:
            return None
            
        config = self.AppKit.NSImageSymbolConfiguration.configurationWithPointSize_weight_(
            point_size, self.AppKit.NSFontWeightRegular
        )
        image = image.imageWithSymbolConfiguration_(config)
        self._cache[key] = image
        return image

class CardFactory:
    def __init__(self, AppKit, symbols: SymbolProvider) -> None:
        self.AppKit = AppKit
        self.symbols = symbols

    def make_card(self, frame, title: str) -> Tuple[object, object]:
        AppKit = self.AppKit
        container = AppKit.NSView.alloc().initWithFrame_(frame)
        container.setWantsLayer_(True)
        if container.layer():
            container.layer().setCornerRadius_(16.0)
            container.layer().setBackgroundColor_(AppKit.NSColor.windowBackgroundColor().colorWithAlphaComponent_(0.5).CGColor())
            container.layer().setBorderWidth_(1.0)
            container.layer().setBorderColor_(AppKit.NSColor.separatorColor().CGColor())

        # Returns (container, content_area)
        # Add basic title
        lbl = _make_label(AppKit, title, 15.0, AppKit.NSFontWeightBold)
        container.addSubview_(lbl)
        
        # Layout title
        AppKit.NSLayoutConstraint.activateConstraints_([
            lbl.leadingAnchor().constraintEqualToAnchor_constant_(container.leadingAnchor(), 20.0),
            lbl.topAnchor().constraintEqualToAnchor_constant_(container.topAnchor(), 20.0),
        ])

        return container, container

class QuickActionsBar:
    def __init__(self, AppKit, symbols: SymbolProvider) -> None:
        self.AppKit = AppKit
        self.symbols = symbols

    def build(self, parent: object, actions: List[QuickAction]) -> Tuple[object, List[object]]:
        AppKit = self.AppKit
        bar = AppKit.NSStackView.stackViewWithViews_([])
        bar.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        bar.setSpacing_(16.0)
        bar.setTranslatesAutoresizingMaskIntoConstraints_(False)
        parent.addSubview_(bar)
        
        AppKit.NSLayoutConstraint.activateConstraints_([
            bar.centerXAnchor().constraintEqualToAnchor_(parent.centerXAnchor()),
            bar.bottomAnchor().constraintEqualToAnchor_constant_(parent.bottomAnchor(), -24.0),
            bar.heightAnchor().constraintEqualToConstant_(44.0),
        ])

        buttons = []
        for action in actions:
            btn = AppKit.NSButton.buttonWithTitle_target_action_(action.title, None, None)
            btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
            image = self.symbols.symbol(action.symbol, 15.0)
            if image:
                btn.setImage_(image)
                btn.setImagePosition_(AppKit.NSImageLeft)
            buttons.append(btn)
            bar.addArrangedSubview_(btn)
            
        return bar, buttons
