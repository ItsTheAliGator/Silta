from __future__ import annotations
from typing import Optional, Callable
from silta.gui.views import _make_label, _make_body_text

class PairingView:
    def __init__(self, coordinator: object, mode: str, peer_name: str, code: Optional[str] = None):
        self.coordinator = coordinator
        self.AppKit = coordinator.AppKit
        self.mode = mode  # 'initiator' or 'receiver'
        self.peer_name = peer_name
        self.code = code
        self.on_code_entered: Optional[Callable[[str], None]] = None
        self.on_cancel: Optional[Callable[[], None]] = None
        self._input_field = None

    def render(self, parent_view: object) -> object:
        AppKit = self.AppKit
        container = AppKit.NSView.alloc().initWithFrame_(parent_view.bounds())
        container.setTranslatesAutoresizingMaskIntoConstraints_(False)
        parent_view.addSubview_(container)

        # Center stack
        stack = AppKit.NSStackView.stackViewWithViews_([])
        stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        stack.setSpacing_(20.0)
        stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        container.addSubview_(stack)

        AppKit.NSLayoutConstraint.activateConstraints_([
            stack.centerXAnchor().constraintEqualToAnchor_(container.centerXAnchor()),
            stack.centerYAnchor().constraintEqualToAnchor_(container.centerYAnchor()),
            stack.widthAnchor().constraintLessThanOrEqualToConstant_(400.0),
        ])

        # Icon
        icon_img = self.coordinator.symbols.symbol("lock.shield", 48.0)
        icon = AppKit.NSImageView.imageViewWithImage_(icon_img)
        icon.setContentTintColor_(AppKit.NSColor.systemBlueColor())
        stack.addArrangedSubview_(icon)

        # Title
        title_text = "Pair with " + self.peer_name
        title = _make_label(AppKit, title_text, 20.0, AppKit.NSFontWeightBold)
        stack.addArrangedSubview_(title)

        if self.mode == 'initiator':
            instr = _make_body_text(AppKit, "Enter this code on the other Mac:")
            stack.addArrangedSubview_(instr)
            
            # Display Code
            code_lbl = _make_label(AppKit, self.code or "ERROR", 36.0, AppKit.NSFontWeightHeavy)
            code_lbl.setTextColor_(AppKit.NSColor.labelColor())
            # Monospaced font if possible
            font = AppKit.NSFont.monospacedDigitSystemFontOfSize_weight_(36.0, AppKit.NSFontWeightHeavy)
            code_lbl.setFont_(font)
            stack.addArrangedSubview_(code_lbl)
            
            # Spinner?
            
        else:
            instr = _make_body_text(AppKit, "Enter the code shown on " + self.peer_name + ":")
            stack.addArrangedSubview_(instr)
            
            # Input Field
            self._input_field = AppKit.NSTextField.alloc().init()
            self._input_field.setTranslatesAutoresizingMaskIntoConstraints_(False)
            self._input_field.setBezelStyle_(AppKit.NSTextFieldSquareBezel)
            self._input_field.setAlignment_(2) # Center
            self._input_field.setFont_(AppKit.NSFont.monospacedDigitSystemFontOfSize_weight_(24.0, AppKit.NSFontWeightRegular))
            self._input_field.setPlaceholderString_("000000")
            
            # Add target action for enter key? For now just a button.
            stack.addArrangedSubview_(self._input_field)
            
            self._input_field.widthAnchor().constraintEqualToConstant_(200.0).setActive_(True)
            self._input_field.heightAnchor().constraintEqualToConstant_(40.0).setActive_(True)

            # Connect Button
            pair_btn = AppKit.NSButton.buttonWithTitle_target_action_("Pair", None, None) # Logic handled by coordinator
            pair_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
            # Hack: assign action to wrapper
            # In real impl, we bind target/action properly.
            stack.addArrangedSubview_(pair_btn)

        # Cancel Button common to both
        cancel_btn = AppKit.NSButton.buttonWithTitle_target_action_("Cancel", None, None)
        cancel_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        stack.addArrangedSubview_(cancel_btn)

        return container
