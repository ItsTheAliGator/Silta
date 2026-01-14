from __future__ import annotations

"""Silta Connection Manager GUI with Liquid Glass effects (macOS 26+).

Modern standalone window for managing Flow connections, monitoring devices,
and controlling Easy-Switch features.

Design upgrades:
- Uses NSGlassEffectView (macOS 26+) for a Liquid Glass backdrop with card overlays
- Falls back to NSVisualEffectView on earlier macOS versions
- Tabbed layout (Overview, Devices, Connection)
- Card sections with subtle shadows and rounded corners
- Simple fade-in animation on load
"""

import os
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import threading
import objc
try:  # macOS 13+ ships QuartzCore; CoreAnimation may not be present in all bindings
    from Quartz import QuartzCore as QC
except ImportError:  # pragma: no cover - depends on host bindings
    QC = None
from Foundation import NSURL

from .capabilities import capabilities_for
from .display_info import get_displays
from .mouse_prefs import read_mouse_speed
from .mac_hid import list_hid_devices
from .pairing import save_profile as save_edge_profile, test_connection as test_server_connection, default_profile_path
from .device_images import create_placeholder_image_nsimage
from .utils import LOG


@dataclass(frozen=True)
class DisplayRow:
    title: str
    subtitle: str
    symbol: str


@dataclass(frozen=True)
class DeviceRow:
    name: str
    subtitle: str
    detail_chips: Sequence[str]
    device_type: str
    vendor_id: int
    product_id: int
    is_builtin: bool


@dataclass(frozen=True)
class DeviceSection:
    heading: str
    rows: Sequence[DeviceRow]


@dataclass(frozen=True)
class OverviewStatus:
    headline: str
    body: str
    hint: str


@dataclass(frozen=True)
class QuickAction:
    identifier: str
    title: str
    symbol: str


@dataclass(frozen=True)
class TabSetup:
    actions: Sequence[QuickAction]
    handlers: Sequence[Callable[[], None]]


class WindowDataProvider:
    """Provide view-friendly data while isolating platform queries."""

    def hostname(self) -> str:
        return socket.gethostname()

    def overview_status(self) -> OverviewStatus:
        return OverviewStatus(
            headline="Not Connected",
            body="Ready to connect to remote machine",
            hint="Use the Connection tab to pair",
        )

    def mouse_speed_text(self) -> str:
        try:
            speed = read_mouse_speed()
        except Exception as err:  # noqa: BLE001
            LOG.debug("Mouse speed unavailable: %s", err)
            return "Unknown"
        if speed is None:
            return "Unknown"
        return f"{speed:.2f}"

    def displays(self) -> List[DisplayRow]:
        rows: List[DisplayRow] = []
        try:
            for display in get_displays()[:4]:
                display_name = display.name or (
                    "Built-in Display" if display.is_builtin else f"Display {display.id}"
                )
                metrics = f"{display.pixels_w}×{display.pixels_h}"
                if display.refresh_hz:
                    metrics += f" @ {display.refresh_hz:.0f}Hz"
                elif display.max_fps:
                    metrics += f" (VRR up to {display.max_fps}Hz)"
                rows.append(
                    DisplayRow(
                        title=display_name,
                        subtitle=metrics,
                        symbol="display",
                    )
                )
        except Exception as err:  # noqa: BLE001
            LOG.exception("Failed to get displays: %s", err)
        return rows

    def device_sections(self) -> Sequence[DeviceSection]:
        try:
            devices = list_hid_devices()
        except Exception as err:  # noqa: BLE001
            LOG.exception("Failed to enumerate devices: %s", err)
            return []

        def rows_for(device_type: str, heading: str) -> DeviceSection:
            filtered = [d for d in devices if d.device_type == device_type][:6]
            rows: List[DeviceRow] = []
            for device in filtered:
                name = device.product or f"VID {device.vendor_id:04X} PID {device.product_id:04X}"
                if len(name) > 40:
                    name = name[:37] + "..."
                location = "Internal" if device.is_builtin else "External"
                caps = capabilities_for(device.vendor_id, device.product_id)
                chips: List[str] = [location]
                chips.extend(c.label for c in caps[:3])
                rows.append(
                    DeviceRow(
                        name=name,
                        subtitle=f"VID {device.vendor_id:04X} · PID {device.product_id:04X}",
                        detail_chips=chips,
                        device_type=device.device_type,
                        vendor_id=device.vendor_id,
                        product_id=device.product_id,
                        is_builtin=device.is_builtin,
                    )
                )
            return DeviceSection(heading=f"{heading} ({len(filtered)})", rows=rows)

        sections: List[DeviceSection] = []
        mice_section = rows_for("mouse", "Mice")
        if mice_section.rows:
            sections.append(mice_section)
        keyboard_section = rows_for("keyboard", "Keyboards")
        if keyboard_section.rows:
            sections.append(keyboard_section)
        return sections

    def profile_path(self) -> str:
        return default_profile_path()


class SymbolProvider:
    """Create SF Symbol images with graceful fallbacks."""

    def __init__(self, AppKit) -> None:
        self._AppKit = AppKit

    def symbol(self, name: str, point_size: float = 22.0) -> Optional[object]:
        if not hasattr(self._AppKit.NSImage, "imageWithSystemSymbolName_accessibilityDescription_"):
            return None
        try:
            config = self._AppKit.NSSymbolConfiguration.configurationWithPointSize_weight_scale_(
                point_size,
                self._AppKit.NSFontWeightMedium,
                self._AppKit.NSImageSymbolScaleMedium,
            )
            image = self._AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
            image = image.imageWithSymbolConfiguration_(config) if image else None
            return image
        except Exception as err:  # noqa: BLE001
            LOG.debug("Could not load symbol %s: %s", name, err)
            return None


class CardFactory:
    """Build card-styled container views with consistent styling."""

    def __init__(self, AppKit, symbol_provider: SymbolProvider) -> None:
        self._AppKit = AppKit
        self._symbols = symbol_provider

    def make_card(self, frame, title: Optional[str] = None) -> Tuple[object, object]:
        AppKit = self._AppKit
        if hasattr(AppKit, "NSGlassEffectView"):
            card = AppKit.NSGlassEffectView.alloc().initWithFrame_(frame)
            try:
                card.setCornerRadius_(16.0)
            except Exception:  # noqa: BLE001
                pass
        else:
            card = AppKit.NSVisualEffectView.alloc().initWithFrame_(frame)
            try:
                card.setMaterial_(AppKit.NSVisualEffectMaterialContentBackground)
                card.setState_(AppKit.NSVisualEffectStateActive)
                card.setBlendingMode_(AppKit.NSVisualEffectBlendingModeWithinWindow)
            except Exception:  # noqa: BLE001
                pass
            try:
                card.setWantsLayer_(True)
                layer = card.layer()
                if layer is not None:
                    layer.setCornerRadius_(16.0)
                    layer.setShadowOpacity_(0.2)
                    layer.setShadowRadius_(14.0)
                    layer.setShadowOffset_(AppKit.NSMakeSize(0, -3))
            except Exception:  # noqa: BLE001
                pass

        content = AppKit.NSView.alloc().initWithFrame_(frame)
        content.setTranslatesAutoresizingMaskIntoConstraints_(False)
        card.addSubview_(content)

        body_container = content

        if title:
            label = AppKit.NSTextField.labelWithString_(title)
            label.setFont_(AppKit.NSFont.systemFontOfSize_weight_(15.0, AppKit.NSFontWeightSemibold))
            label.setTextColor_(AppKit.NSColor.labelColor())
            label.setTranslatesAutoresizingMaskIntoConstraints_(False)
            content.addSubview_(label)
            AppKit.NSLayoutConstraint.activateConstraints_([
                label.leadingAnchor().constraintEqualToAnchor_constant_(content.leadingAnchor(), 24.0),
                label.topAnchor().constraintEqualToAnchor_constant_(content.topAnchor(), 20.0),
            ])
            separator = AppKit.NSBox.alloc().init()
            separator.setBoxType_(AppKit.NSBoxSeparator)
            separator.setTranslatesAutoresizingMaskIntoConstraints_(False)
            content.addSubview_(separator)
            AppKit.NSLayoutConstraint.activateConstraints_([
                separator.leadingAnchor().constraintEqualToAnchor_constant_(content.leadingAnchor(), 24.0),
                separator.trailingAnchor().constraintEqualToAnchor_constant_(content.trailingAnchor(), -24.0),
                separator.topAnchor().constraintEqualToAnchor_constant_(label.bottomAnchor(), 12.0),
            ])

            body_container = AppKit.NSView.alloc().init()
            body_container.setTranslatesAutoresizingMaskIntoConstraints_(False)
            content.addSubview_(body_container)
            AppKit.NSLayoutConstraint.activateConstraints_([
                body_container.leadingAnchor().constraintEqualToAnchor_(content.leadingAnchor()),
                body_container.trailingAnchor().constraintEqualToAnchor_(content.trailingAnchor()),
                body_container.bottomAnchor().constraintEqualToAnchor_(content.bottomAnchor()),
                body_container.topAnchor().constraintEqualToAnchor_constant_(separator.bottomAnchor(), 20.0),
            ])

        AppKit.NSLayoutConstraint.activateConstraints_([
            content.leadingAnchor().constraintEqualToAnchor_constant_(card.leadingAnchor(), 0.0),
            content.trailingAnchor().constraintEqualToAnchor_constant_(card.trailingAnchor(), 0.0),
            content.topAnchor().constraintEqualToAnchor_constant_(card.topAnchor(), 0.0),
            content.bottomAnchor().constraintEqualToAnchor_constant_(card.bottomAnchor(), 0.0),
        ])

        return card, body_container

    def symbol_badge(self, symbol_name: str, size: float = 14.0) -> Optional[object]:
        return self._symbols.symbol(symbol_name, size)


class QuickActionsBar:
    """Pinned quick actions for convenient commands."""

    def __init__(self, AppKit, symbol_provider: SymbolProvider) -> None:
        self._AppKit = AppKit
        self._symbols = symbol_provider

    def build(self, parent: object, actions: Sequence[QuickAction]) -> Tuple[object, Sequence[object]]:
        AppKit = self._AppKit
        bar = AppKit.NSVisualEffectView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 100, 60))
        try:
            bar.setMaterial_(AppKit.NSVisualEffectMaterialToolTip)
            bar.setState_(AppKit.NSVisualEffectStateActive)
        except Exception:  # noqa: BLE001
            pass
        bar.setTranslatesAutoresizingMaskIntoConstraints_(False)
        parent.addSubview_(bar)

        stack = AppKit.NSStackView.stackViewWithViews_([])
        stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        stack.setAlignment_(AppKit.NSLayoutAttributeCenterY)
        stack.setSpacing_(12.0)
        stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        bar.addSubview_(stack)

        buttons: List[object] = []
        for idx, quick_action in enumerate(actions):
            btn = AppKit.NSButton.buttonWithTitle_target_action_(quick_action.title, None, None)
            btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
            btn.setTranslatesAutoresizingMaskIntoConstraints_(False)
            btn.setTag_(idx)
            image = self._symbols.symbol(quick_action.symbol, 15.0)
            if image is not None:
                btn.setImage_(image)
                btn.setImagePosition_(AppKit.NSImageLeft)
            stack.addArrangedSubview_(btn)
            buttons.append(btn)

        AppKit.NSLayoutConstraint.activateConstraints_([
            bar.leadingAnchor().constraintEqualToAnchor_constant_(parent.leadingAnchor(), 24.0),
            bar.trailingAnchor().constraintEqualToAnchor_constant_(parent.trailingAnchor(), -24.0),
            bar.bottomAnchor().constraintEqualToAnchor_constant_(parent.bottomAnchor(), -24.0),
            bar.heightAnchor().constraintEqualToConstant_(56.0),
            stack.centerXAnchor().constraintEqualToAnchor_(bar.centerXAnchor()),
            stack.centerYAnchor().constraintEqualToAnchor_(bar.centerYAnchor()),
        ])

        return bar, buttons

_WINDOW_SINGLETON: Optional[object] = None
_CONTENT_SINGLETON: Optional[object] = None

_CallbackTargetClass: Optional[type] = None
_ActionDispatcherClass: Optional[type] = None


def _ensure_objc_helpers(AppKit):
    global _CallbackTargetClass, _ActionDispatcherClass
    if _CallbackTargetClass is not None and _ActionDispatcherClass is not None:
        return _CallbackTargetClass, _ActionDispatcherClass
    try:
        _CallbackTargetClass = objc.lookUpClass("SiltaCallbackTarget")
        _ActionDispatcherClass = objc.lookUpClass("SiltaActionDispatcher")
        return _CallbackTargetClass, _ActionDispatcherClass
    except Exception:  # noqa: BLE001
        pass

    class SiltaCallbackTarget(AppKit.NSObject):  # type: ignore[misc]
        @objc.signature(b"@@:@")
        def initWithCallback_(self, callback):
            self = objc.super(SiltaCallbackTarget, self).init()
            if self is None:
                return None
            self._callback = callback
            return self

        @objc.signature(b"v@:@")
        def invoke_(self, _sender):  # noqa: N802
            callback = getattr(self, "_callback", None)
            if callback is not None:
                try:
                    callback()
                except Exception as exc:  # noqa: BLE001
                    LOG.exception("Button callback failed: %s", exc)

    class SiltaActionDispatcher(AppKit.NSObject):  # type: ignore[misc]
        @objc.signature(b"@@:@")
        def initWithHandlers_(self, handlers):
            self = objc.super(SiltaActionDispatcher, self).init()
            if self is None:
                return None
            self._handlers = list(handlers)
            return self

        @objc.signature(b"v@:@")
        def trigger_(self, sender):  # noqa: N802
            try:
                tag = int(sender.tag())
            except Exception:  # noqa: BLE001
                tag = -1
            if 0 <= tag < len(self._handlers):
                try:
                    self._handlers[tag]()
                except Exception as exc:  # noqa: BLE001
                    LOG.exception("Quick action failed: %s", exc)

        @objc.signature(b"v@:@")
        def updateHandlers_(self, handlers):  # noqa: N802
            self._handlers = list(handlers)

    _CallbackTargetClass = SiltaCallbackTarget
    _ActionDispatcherClass = SiltaActionDispatcher
    return _CallbackTargetClass, _ActionDispatcherClass


def _create_glass_window(AppKit, title: str = "Silta Connection Manager") -> tuple:
    """
    Create a window with Liquid Glass effect (macOS 26+).
    
    Returns: (window, content_view, glass_view)
    """
    # Create window with standard style
    window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        AppKit.NSMakeRect(100, 100, 800, 600),
        AppKit.NSWindowStyleMaskTitled | 
        AppKit.NSWindowStyleMaskClosable | 
        AppKit.NSWindowStyleMaskMiniaturizable | 
        AppKit.NSWindowStyleMaskResizable,
        AppKit.NSBackingStoreBuffered,
        False
    )
    window.setTitle_(title)
    
    # Try to use NSGlassEffectView (macOS 26+)
    try:
        # Check if NSGlassEffectView is available
        if hasattr(AppKit, "NSGlassEffectView"):
            LOG.info("Using NSGlassEffectView (macOS 26+ Liquid Glass)")

            # Create glass effect view as background
            glass_view = AppKit.NSGlassEffectView.alloc().initWithFrame_(window.contentView().bounds())

            # Try to set style if available
            if hasattr(AppKit, "NSGlassEffectViewStyle"):
                # Use default/automatic style
                try:
                    glass_view.setStyle_(0)  # NSGlassEffectViewStyleAutomatic
                except Exception as exc:  # noqa: BLE001
                    LOG.debug("Could not set glass style: %s", exc)
            # Slight tint for depth
            try:
                glass_view.setCornerRadius_(12.0)
            except Exception:  # noqa: BLE001
                pass

            glass_view.setTranslatesAutoresizingMaskIntoConstraints_(False)

            # Add to window and use it directly as content
            window.contentView().addSubview_(glass_view)
            content_view = glass_view  # Use glass view directly, no extra layer

        else:
            # Fallback to NSVisualEffectView (macOS 10.10+)
            LOG.info("NSGlassEffectView not available, using NSVisualEffectView fallback")
            glass_view = _create_visual_effect_fallback(AppKit, window)
            glass_view.setTranslatesAutoresizingMaskIntoConstraints_(False)
            content_view = glass_view  # Use visual effect view directly

        # Pin the glass/visual view to fill the window content
        parent = window.contentView()
        AppKit.NSLayoutConstraint.activateConstraints_([
            glass_view.leadingAnchor().constraintEqualToAnchor_(parent.leadingAnchor()),
            glass_view.trailingAnchor().constraintEqualToAnchor_(parent.trailingAnchor()),
            glass_view.topAnchor().constraintEqualToAnchor_(parent.topAnchor()),
            glass_view.bottomAnchor().constraintEqualToAnchor_(parent.bottomAnchor()),
        ])

        _apply_background_gradient(AppKit, content_view)

    except Exception as exc:  # noqa: BLE001
        LOG.warning("Could not create glass effect: %s, using standard window", exc)
        glass_view = None
        content_view = window.contentView()

    return window, content_view, glass_view


def _create_visual_effect_fallback(AppKit, window):
    """Create NSVisualEffectView as fallback for older macOS versions."""
    visual_effect = AppKit.NSVisualEffectView.alloc().initWithFrame_(window.contentView().bounds())
    
    # Set material to window background (translucent)
    visual_effect.setMaterial_(AppKit.NSVisualEffectMaterialUnderWindowBackground)
    
    # Set blending mode
    visual_effect.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
    
    # Set state to active for best appearance
    visual_effect.setState_(AppKit.NSVisualEffectStateActive)
    visual_effect.setTranslatesAutoresizingMaskIntoConstraints_(False)

    window.contentView().addSubview_(visual_effect)
    return visual_effect


def _apply_background_gradient(AppKit, target_view) -> None:
    """Add a subtle gradient for depth behind the UI stack."""
    if QC is None:
        return
    try:
        target_view.setWantsLayer_(True)
        base_layer = target_view.layer()
        if base_layer is None:
            base_layer = QC.CALayer.layer()
            target_view.setLayer_(base_layer)

        gradient = QC.CAGradientLayer.layer()
        gradient.setName_("silta.backgroundGradient")
        gradient.setFrame_(target_view.bounds())
        gradient.setNeedsDisplayOnBoundsChange_(True)

        srgb = AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_
        gradient.setColors_([
            srgb(0.08, 0.09, 0.12, 0.95).CGColor(),
            srgb(0.10, 0.11, 0.16, 0.60).CGColor(),
            srgb(0.05, 0.05, 0.07, 0.90).CGColor(),
        ])
        gradient.setLocations_([0.0, 0.55, 1.0])
        gradient.setStartPoint_(AppKit.NSMakePoint(0.2, 1.0))
        gradient.setEndPoint_(AppKit.NSMakePoint(0.8, 0.0))

        base_layer.insertSublayer_atIndex_(gradient, 0)
    except Exception as exc:  # noqa: BLE001
        LOG.debug("Unable to apply gradient: %s", exc)


def _make_label(AppKit, text: str, size: float, weight: float = None, color=None) -> object:
    """Create a consistently styled label for auto layout usage."""
    label = AppKit.NSTextField.labelWithString_(text)
    weight = weight if weight is not None else AppKit.NSFontWeightRegular
    label.setFont_(AppKit.NSFont.systemFontOfSize_weight_(size, weight))
    label.setTextColor_(color or AppKit.NSColor.labelColor())
    label.setTranslatesAutoresizingMaskIntoConstraints_(False)
    return label
def _make_body_text(AppKit, text: str, size: float = 13.0, color=None) -> object:
    label = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 10, 10))
    label.setStringValue_(text)
    label.setEditable_(False)
    label.setSelectable_(False)
    label.setBordered_(False)
    label.setDrawsBackground_(False)
    label.setFont_(AppKit.NSFont.systemFontOfSize_weight_(size, AppKit.NSFontWeightRegular))
    label.setTextColor_(color or AppKit.NSColor.secondaryLabelColor())
    label.setLineBreakMode_(AppKit.NSLineBreakByWordWrapping)
    label.setMaximumNumberOfLines_(0)
    label.setTranslatesAutoresizingMaskIntoConstraints_(False)
    return label


def _make_chip(AppKit, text: str) -> object:
    chip = AppKit.NSTextField.labelWithString_(text)
    chip.setFont_(AppKit.NSFont.systemFontOfSize_weight_(11.0, AppKit.NSFontWeightSemibold))
    chip.setTextColor_(AppKit.NSColor.controlAccentColor())
    chip.setTranslatesAutoresizingMaskIntoConstraints_(False)
    chip.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
    chip.setWantsLayer_(True)
    layer = chip.layer()
    if layer is not None:
        accent = AppKit.NSColor.controlAccentColor().colorWithAlphaComponent_(0.18)
        layer.setBackgroundColor_(accent.CGColor())
        layer.setCornerRadius_(10.0)
    chip.setAlignment_(AppKit.NSTextAlignmentCenter)
    chip.setContentHuggingPriority_forOrientation_(251, AppKit.NSLayoutConstraintOrientationHorizontal)
    chip.setContentCompressionResistancePriority_forOrientation_(752, AppKit.NSLayoutConstraintOrientationHorizontal)
    AppKit.NSLayoutConstraint.activateConstraints_([
        chip.heightAnchor().constraintGreaterThanOrEqualToConstant_(20.0),
    ])
    return chip


def _limit_width(AppKit, view: object, max_width: float) -> None:
    constraint = view.widthAnchor().constraintLessThanOrEqualToConstant_(max_width)
    constraint.setActive_(True)


class _StackTabBuilder:
    """Base class for tabs that renders into a scrolling stack view."""

    def __init__(self, coordinator: "ConnectionWindowCoordinator") -> None:
        self._coordinator = coordinator
        self._AppKit = coordinator.AppKit
        self._cards = coordinator.card_factory
        self._data = coordinator.data_provider
        self._symbols = coordinator.symbols
        self._scroll_view: Optional[object] = None
        self._stack: Optional[object] = None
        self._root_view: Optional[object] = None

    def render(self, parent_view: object) -> Tuple[TabSetup, object]:
        self._root_view = parent_view
        if self._scroll_view is None:
            self._scroll_view, self._stack = self._prepare_scroll_stack(parent_view)
        else:
            self._clear_stack()
        setup = self._populate()
        return setup, self._scroll_view

    def refresh(self) -> TabSetup:
        if self._stack is None:
            raise RuntimeError("Tab has not been rendered yet")
        self._clear_stack()
        return self._populate()

    def _prepare_scroll_stack(self, parent_view: object) -> Tuple[object, object]:
        AppKit = self._AppKit
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 100, 100))
        scroll.setDrawsBackground_(False)
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setTranslatesAutoresizingMaskIntoConstraints_(False)
        parent_view.addSubview_(scroll)
        AppKit.NSLayoutConstraint.activateConstraints_([
            scroll.leadingAnchor().constraintEqualToAnchor_constant_(parent_view.leadingAnchor(), 24.0),
            scroll.trailingAnchor().constraintEqualToAnchor_constant_(parent_view.trailingAnchor(), -24.0),
            scroll.topAnchor().constraintEqualToAnchor_constant_(parent_view.topAnchor(), 24.0),
        ])

        clip = scroll.contentView()
        document = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 100, 100))
        document.setTranslatesAutoresizingMaskIntoConstraints_(False)
        scroll.setDocumentView_(document)

        stack = AppKit.NSStackView.stackViewWithViews_([])
        stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        stack.setAlignment_(AppKit.NSLayoutAttributeCenterX)
        stack.setSpacing_(24.0)
        stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        document.addSubview_(stack)

        AppKit.NSLayoutConstraint.activateConstraints_([
            document.leadingAnchor().constraintEqualToAnchor_(clip.leadingAnchor()),
            document.trailingAnchor().constraintEqualToAnchor_(clip.trailingAnchor()),
            document.topAnchor().constraintEqualToAnchor_(clip.topAnchor()),
            document.bottomAnchor().constraintGreaterThanOrEqualToAnchor_(clip.bottomAnchor()),
            document.widthAnchor().constraintEqualToAnchor_(clip.widthAnchor()),
            stack.leadingAnchor().constraintEqualToAnchor_(document.leadingAnchor()),
            stack.trailingAnchor().constraintEqualToAnchor_(document.trailingAnchor()),
            stack.topAnchor().constraintEqualToAnchor_(document.topAnchor()),
            stack.bottomAnchor().constraintLessThanOrEqualToAnchor_(document.bottomAnchor()),
        ])

        self._stack = stack
        return scroll, stack

    def _clear_stack(self) -> None:
        if self._stack is None:
            return
        arranged = list(self._stack.arrangedSubviews())  # type: ignore[attr-defined]
        for view in arranged:
            self._stack.removeArrangedSubview_(view)  # type: ignore[func-returns-value]
            view.removeFromSuperview()

    def _populate(self) -> TabSetup:
        raise NotImplementedError


class OverviewTabBuilder(_StackTabBuilder):
    def _populate(self) -> TabSetup:
        AppKit = self._AppKit
        assert self._stack is not None
        stack = self._stack

        hostname = self._data.hostname()
        title_row = AppKit.NSStackView.stackViewWithViews_([])
        title_row.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        title_row.setAlignment_(AppKit.NSLayoutAttributeCenterY)
        title_row.setSpacing_(12.0)
        title_row.setTranslatesAutoresizingMaskIntoConstraints_(False)
        stack.addArrangedSubview_(title_row)

        icon_view = AppKit.NSImageView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 28, 28))
        icon_view.setTranslatesAutoresizingMaskIntoConstraints_(False)
        desktop_icon = self._symbols.symbol("desktopcomputer", 22.0)
        if desktop_icon is not None:
            icon_view.setImage_(desktop_icon)
            try:
                icon_view.setContentTintColor_(AppKit.NSColor.secondaryLabelColor())
            except Exception:  # noqa: BLE001
                pass
        AppKit.NSLayoutConstraint.activateConstraints_([
            icon_view.widthAnchor().constraintEqualToConstant_(28.0),
            icon_view.heightAnchor().constraintEqualToConstant_(28.0),
        ])
        title_row.addArrangedSubview_(icon_view)
        title_row.addArrangedSubview_(_make_label(AppKit, hostname, 24.0, AppKit.NSFontWeightSemibold))

        hero_card, hero_body = self._cards.make_card(AppKit.NSMakeRect(0, 0, 760, 200))
        hero_card.setTranslatesAutoresizingMaskIntoConstraints_(False)
        _limit_width(AppKit, hero_card, 880.0)
        stack.addArrangedSubview_(hero_card)

        hero_stack = AppKit.NSStackView.stackViewWithViews_([])
        hero_stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        hero_stack.setAlignment_(AppKit.NSLayoutAttributeCenterY)
        hero_stack.setDistribution_(AppKit.NSStackViewDistributionFillProportionally)
        hero_stack.setSpacing_(28.0)
        hero_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        hero_body.addSubview_(hero_stack)
        AppKit.NSLayoutConstraint.activateConstraints_([
            hero_stack.leadingAnchor().constraintEqualToAnchor_constant_(hero_body.leadingAnchor(), 24.0),
            hero_stack.trailingAnchor().constraintEqualToAnchor_constant_(hero_body.trailingAnchor(), -24.0),
            hero_stack.topAnchor().constraintEqualToAnchor_constant_(hero_body.topAnchor(), 24.0),
            hero_stack.bottomAnchor().constraintEqualToAnchor_constant_(hero_body.bottomAnchor(), -24.0),
        ])

        status = self._data.overview_status()
        left = AppKit.NSStackView.stackViewWithViews_([])
        left.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        left.setSpacing_(6.0)
        left.setTranslatesAutoresizingMaskIntoConstraints_(False)
        hero_stack.addArrangedSubview_(left)

        status_row = AppKit.NSStackView.stackViewWithViews_([])
        status_row.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        status_row.setAlignment_(AppKit.NSLayoutAttributeCenterY)
        status_row.setSpacing_(8.0)
        status_row.setTranslatesAutoresizingMaskIntoConstraints_(False)
        left.addArrangedSubview_(status_row)

        indicator = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 14, 14))
        indicator.setTranslatesAutoresizingMaskIntoConstraints_(False)
        indicator.setWantsLayer_(True)
        layer = indicator.layer()
        if layer is not None:
            layer.setCornerRadius_(7.0)
            layer.setBackgroundColor_(AppKit.NSColor.systemGrayColor().colorWithAlphaComponent_(0.85).CGColor())
        status_row.addArrangedSubview_(indicator)
        AppKit.NSLayoutConstraint.activateConstraints_([
            indicator.widthAnchor().constraintEqualToConstant_(14.0),
            indicator.heightAnchor().constraintEqualToConstant_(14.0),
        ])

        status_row.addArrangedSubview_(_make_label(AppKit, status.headline, 28.0, AppKit.NSFontWeightSemibold))
        left.addArrangedSubview_(_make_label(AppKit, status.body, 14.0, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor()))
        left.addArrangedSubview_(_make_label(AppKit, status.hint, 12.0, AppKit.NSFontWeightRegular, AppKit.NSColor.tertiaryLabelColor()))

        right = AppKit.NSStackView.stackViewWithViews_([])
        right.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        right.setSpacing_(12.0)
        right.setTranslatesAutoresizingMaskIntoConstraints_(False)
        hero_stack.addArrangedSubview_(right)

        cta_button = self._coordinator.create_button(
            "Open Connection Tab",
            lambda: self._coordinator.select_tab("Connection"),
            symbol="link"
        )
        right.addArrangedSubview_(cta_button)

        info_row = AppKit.NSStackView.stackViewWithViews_([])
        info_row.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        info_row.setSpacing_(24.0)
        info_row.setTranslatesAutoresizingMaskIntoConstraints_(False)
        stack.addArrangedSubview_(info_row)

        local_card, local_body = self._cards.make_card(AppKit.NSMakeRect(0, 0, 360, 160), "Local Settings")
        local_card.setTranslatesAutoresizingMaskIntoConstraints_(False)
        _limit_width(AppKit, local_card, 420.0)
        info_row.addArrangedSubview_(local_card)
        local_stack = AppKit.NSStackView.stackViewWithViews_([])
        local_stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        local_stack.setSpacing_(6.0)
        local_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        local_body.addSubview_(local_stack)
        AppKit.NSLayoutConstraint.activateConstraints_([
            local_stack.leadingAnchor().constraintEqualToAnchor_constant_(local_body.leadingAnchor(), 24.0),
            local_stack.trailingAnchor().constraintEqualToAnchor_constant_(local_body.trailingAnchor(), -24.0),
            local_stack.topAnchor().constraintEqualToAnchor_constant_(local_body.topAnchor(), 18.0),
            local_stack.bottomAnchor().constraintLessThanOrEqualToAnchor_constant_(local_body.bottomAnchor(), -18.0),
        ])
        local_stack.addArrangedSubview_(_make_label(AppKit, "Mouse Speed", 12.0, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor()))
        local_stack.addArrangedSubview_(_make_label(AppKit, self._data.mouse_speed_text(), 22.0, AppKit.NSFontWeightSemibold))

        profile_card, profile_body = self._cards.make_card(AppKit.NSMakeRect(0, 0, 360, 160), "Edge Profiles")
        profile_card.setTranslatesAutoresizingMaskIntoConstraints_(False)
        _limit_width(AppKit, profile_card, 420.0)
        info_row.addArrangedSubview_(profile_card)
        profile_stack = AppKit.NSStackView.stackViewWithViews_([])
        profile_stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        profile_stack.setSpacing_(6.0)
        profile_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        profile_body.addSubview_(profile_stack)
        AppKit.NSLayoutConstraint.activateConstraints_([
            profile_stack.leadingAnchor().constraintEqualToAnchor_constant_(profile_body.leadingAnchor(), 24.0),
            profile_stack.trailingAnchor().constraintEqualToAnchor_constant_(profile_body.trailingAnchor(), -24.0),
            profile_stack.topAnchor().constraintEqualToAnchor_constant_(profile_body.topAnchor(), 18.0),
            profile_stack.bottomAnchor().constraintLessThanOrEqualToAnchor_constant_(profile_body.bottomAnchor(), -18.0),
        ])
        profile_stack.addArrangedSubview_(_make_body_text(AppKit, str(Path(self._data.profile_path())), 12.0, AppKit.NSColor.tertiaryLabelColor()))

        displays_card, displays_body = self._cards.make_card(AppKit.NSMakeRect(0, 0, 760, 220), "Displays")
        displays_card.setTranslatesAutoresizingMaskIntoConstraints_(False)
        _limit_width(AppKit, displays_card, 980.0)
        stack.addArrangedSubview_(displays_card)

        display_stack = AppKit.NSStackView.stackViewWithViews_([])
        display_stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        display_stack.setSpacing_(12.0)
        display_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        displays_body.addSubview_(display_stack)
        AppKit.NSLayoutConstraint.activateConstraints_([
            display_stack.leadingAnchor().constraintEqualToAnchor_constant_(displays_body.leadingAnchor(), 24.0),
            display_stack.trailingAnchor().constraintEqualToAnchor_constant_(displays_body.trailingAnchor(), -24.0),
            display_stack.topAnchor().constraintEqualToAnchor_constant_(displays_body.topAnchor(), 16.0),
            display_stack.bottomAnchor().constraintLessThanOrEqualToAnchor_constant_(displays_body.bottomAnchor(), -16.0),
        ])

        displays = self._data.displays()
        if not displays:
            display_stack.addArrangedSubview_(_make_label(AppKit, "No displays detected", 13.0, AppKit.NSFontWeightRegular, AppKit.NSColor.secondaryLabelColor()))
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


class DevicesTabBuilder(_StackTabBuilder):
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


class ConnectionTabBuilder(_StackTabBuilder):
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


class PairingSheetPresenter:
    def __init__(self, coordinator: "ConnectionWindowCoordinator") -> None:
        self._coordinator = coordinator
        self._AppKit = coordinator.AppKit
        self._window = coordinator.window

    def present(self) -> None:
        AppKit = self._AppKit
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_("Pair another machine")
        alert.setInformativeText_("Enter connection details. We'll save the edge profile and test connectivity.")

        accessory = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 380, 200))
        alert.setAccessoryView_(accessory)

        column = AppKit.NSStackView.stackViewWithViews_([])
        column.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        column.setSpacing_(8.0)
        column.setTranslatesAutoresizingMaskIntoConstraints_(False)
        accessory.addSubview_(column)
        AppKit.NSLayoutConstraint.activateConstraints_([
            column.leadingAnchor().constraintEqualToAnchor_(accessory.leadingAnchor()),
            column.trailingAnchor().constraintEqualToAnchor_(accessory.trailingAnchor()),
            column.topAnchor().constraintEqualToAnchor_(accessory.topAnchor()),
            column.bottomAnchor().constraintEqualToAnchor_(accessory.bottomAnchor()),
        ])

        def field_row(label_text: str, placeholder: str, default: Optional[str] = None) -> object:
            row = AppKit.NSStackView.stackViewWithViews_([])
            row.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
            row.setSpacing_(12.0)
            row.setAlignment_(AppKit.NSLayoutAttributeCenterY)
            row.setTranslatesAutoresizingMaskIntoConstraints_(False)
            label = _make_label(AppKit, label_text, 12.0, AppKit.NSFontWeightSemibold, AppKit.NSColor.secondaryLabelColor())
            label.setAlignment_(AppKit.NSTextAlignmentRight)
            label.setContentHuggingPriority_forOrientation_(260, AppKit.NSLayoutConstraintOrientationHorizontal)
            row.addArrangedSubview_(label)
            field = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 240, 24))
            field.setTranslatesAutoresizingMaskIntoConstraints_(False)
            field.setPlaceholderString_(placeholder)
            if default:
                field.setStringValue_(default)
            AppKit.NSLayoutConstraint.activateConstraints_([
                field.widthAnchor().constraintGreaterThanOrEqualToConstant_(240.0),
            ])
            row.addArrangedSubview_(field)
            column.addArrangedSubview_(row)
            return field

        host_field = field_row("Host", "remote.example.com", None)
        port_field = field_row("Port", "59873", "59873")

        token_row = AppKit.NSStackView.stackViewWithViews_([])
        token_row.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        token_row.setSpacing_(12.0)
        token_row.setAlignment_(AppKit.NSLayoutAttributeCenterY)
        token_row.setTranslatesAutoresizingMaskIntoConstraints_(False)
        token_label = _make_label(AppKit, "Token", 12.0, AppKit.NSFontWeightSemibold, AppKit.NSColor.secondaryLabelColor())
        token_label.setAlignment_(AppKit.NSTextAlignmentRight)
        token_label.setContentHuggingPriority_forOrientation_(260, AppKit.NSLayoutConstraintOrientationHorizontal)
        token_row.addArrangedSubview_(token_label)
        token_field = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 240, 24))
        token_field.setPlaceholderString_("Optional access token")
        token_field.setTranslatesAutoresizingMaskIntoConstraints_(False)
        AppKit.NSLayoutConstraint.activateConstraints_([
            token_field.widthAnchor().constraintGreaterThanOrEqualToConstant_(240.0),
        ])
        token_row.addArrangedSubview_(token_field)
        column.addArrangedSubview_(token_row)

        edge_row = AppKit.NSStackView.stackViewWithViews_([])
        edge_row.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        edge_row.setSpacing_(12.0)
        edge_row.setAlignment_(AppKit.NSLayoutAttributeCenterY)
        edge_row.setTranslatesAutoresizingMaskIntoConstraints_(False)
        edge_label = _make_label(AppKit, "Edge", 12.0, AppKit.NSFontWeightSemibold, AppKit.NSColor.secondaryLabelColor())
        edge_label.setAlignment_(AppKit.NSTextAlignmentRight)
        edge_label.setContentHuggingPriority_forOrientation_(260, AppKit.NSLayoutConstraintOrientationHorizontal)
        edge_row.addArrangedSubview_(edge_label)
        edge_popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(AppKit.NSMakeRect(0, 0, 180, 26), False)
        edge_popup.addItemsWithTitles_(["default", "left", "right", "top", "bottom"])
        edge_popup.selectItemAtIndex_(0)
        edge_popup.setTranslatesAutoresizingMaskIntoConstraints_(False)
        edge_row.addArrangedSubview_(edge_popup)
        column.addArrangedSubview_(edge_row)

        column.addArrangedSubview_(_make_body_text(AppKit, "Tokens are optional. Leave blank if your server does not require authentication.", 11.0, AppKit.NSColor.tertiaryLabelColor()))

        alert.addButtonWithTitle_("Save & Test")
        alert.addButtonWithTitle_("Cancel")

        response = alert.runModal()
        if response != AppKit.NSAlertFirstButtonReturn:
            return

        host = host_field.stringValue().strip()  # type: ignore[attr-defined]
        port_value = port_field.stringValue().strip()  # type: ignore[attr-defined]
        token = token_field.stringValue().strip() or None  # type: ignore[attr-defined]
        edge = edge_popup.titleOfSelectedItem() or "default"

        try:
            port = int(port_value)
        except ValueError:
            port = 59873

        progress_alert = AppKit.NSAlert.alloc().init()
        progress_alert.setMessageText_("Testing connection…")
        progress_alert.setInformativeText_(f"Connecting to {host}:{port}")
        spinner_container = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 60, 40))
        spinner_container.setTranslatesAutoresizingMaskIntoConstraints_(False)
        spinner = AppKit.NSProgressIndicator.alloc().initWithFrame_(AppKit.NSMakeRect(20, 10, 20, 20))
        spinner.setStyle_(AppKit.NSProgressIndicatorStyleSpinning)
        spinner.setTranslatesAutoresizingMaskIntoConstraints_(False)
        spinner.startAnimation_(None)
        spinner_container.addSubview_(spinner)
        AppKit.NSLayoutConstraint.activateConstraints_([
            spinner.centerXAnchor().constraintEqualToAnchor_(spinner_container.centerXAnchor()),
            spinner.centerYAnchor().constraintEqualToAnchor_(spinner_container.centerYAnchor()),
        ])
        progress_alert.setAccessoryView_(spinner_container)
        progress_alert.beginSheetModalForWindow_completionHandler_(self._window, None)

        result: List[Optional[str]] = [None, None, None]

        def worker() -> None:
            ok, message = test_server_connection(host, port, token, timeout=3.0)
            result[0] = "ok" if ok else "fail"
            result[1] = message
            try:
                result[2] = save_edge_profile(edge, host, port, token)
            except Exception as exc:  # noqa: BLE001
                result[2] = str(exc)
            AppKit.NSApp.performSelectorOnMainThread_withObject_waitUntilDone_("stopModal", None, False)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        AppKit.NSApp.runModalForWindow_(progress_alert.window())
        progress_alert.window().orderOut_(None)
        thread.join(timeout=1.0)

        success = result[0] == "ok"
        message = result[1] or "No response"
        destination = result[2] or self._coordinator.data_provider.profile_path()

        outcome = AppKit.NSAlert.alloc().init()
        if success:
            outcome.setMessageText_("Paired successfully")
            outcome.setAlertStyle_(AppKit.NSAlertStyleInformational)
            outcome.setInformativeText_(f"{message}\n\nProfile saved to:\n{destination}")
        else:
            outcome.setMessageText_("Connection test failed")
            outcome.setAlertStyle_(AppKit.NSAlertStyleWarning)
            outcome.setInformativeText_(f"{message}\n\nProfile saved to:\n{destination}\n\nCheck that the Silta server is running on the remote machine.")
        outcome.addButtonWithTitle_("OK")
        outcome.beginSheetModalForWindow_completionHandler_(self._window, None)


class ConnectionWindowCoordinator:
    def __init__(self, AppKit, window, content_view) -> None:
        self.AppKit = AppKit
        self.window = window
        self.content_view = content_view
        self.data_provider = WindowDataProvider()
        self.symbols = SymbolProvider(AppKit)
        self.card_factory = CardFactory(AppKit, self.symbols)
        self.quick_actions_bar = QuickActionsBar(AppKit, self.symbols)
        self.builders: dict[str, _StackTabBuilder] = {}
        self.tab_items: dict[str, object] = {}
        self._quick_action_state: dict[str, Tuple[object, Sequence[object], object, object, TabSetup]] = {}
        self._callback_targets: List[object] = []
        self._action_dispatchers: List[object] = []
        self._pairing_presenter = PairingSheetPresenter(self)
        self._callback_target_class, self._action_dispatcher_class = _ensure_objc_helpers(AppKit)

    def build(self) -> None:
        AppKit = self.AppKit
        tab = AppKit.NSTabView.alloc().initWithFrame_(self.content_view.bounds())
        tab.setTranslatesAutoresizingMaskIntoConstraints_(False)
        self.content_view.addSubview_(tab)
        AppKit.NSLayoutConstraint.activateConstraints_([
            tab.leadingAnchor().constraintEqualToAnchor_(self.content_view.leadingAnchor()),
            tab.trailingAnchor().constraintEqualToAnchor_(self.content_view.trailingAnchor()),
            tab.topAnchor().constraintEqualToAnchor_(self.content_view.topAnchor()),
            tab.bottomAnchor().constraintEqualToAnchor_(self.content_view.bottomAnchor()),
        ])
        self.tab_view = tab

        tab_defs = [
            ("Overview", OverviewTabBuilder, "rectangle.grid.2x2"),
            ("Devices", DevicesTabBuilder, "keyboard"),
            ("Connection", ConnectionTabBuilder, "link"),
        ]

        for label, builder_cls, symbol in tab_defs:
            item = AppKit.NSTabViewItem.alloc().initWithIdentifier_(label)
            item.setLabel_(label)
            view = AppKit.NSView.alloc().initWithFrame_(self.content_view.bounds())
            view.setTranslatesAutoresizingMaskIntoConstraints_(False)
            item.setView_(view)
            icon = self.symbols.symbol(symbol, 16.0)
            if icon is not None:
                item.setImage_(icon)
            tab.addTabViewItem_(item)
            builder = builder_cls(self)
            setup, scroll = builder.render(view)
            self.builders[label] = builder
            self.tab_items[label] = item
            self._attach_quick_actions(label, view, setup, scroll)

    def _attach_quick_actions(self, label: str, parent_view: object, setup: TabSetup, scroll: object) -> None:
        bar, buttons = self.quick_actions_bar.build(parent_view, setup.actions)
        dispatcher = self._action_dispatcher_class.alloc().initWithHandlers_(setup.handlers)
        for button in buttons:
            button.setTarget_(dispatcher)
            button.setAction_("trigger:")
        self._action_dispatchers.append(dispatcher)
        self._quick_action_state[label] = (bar, buttons, dispatcher, scroll, setup)
        self.AppKit.NSLayoutConstraint.activateConstraints_([
            scroll.bottomAnchor().constraintEqualToAnchor_constant_(bar.topAnchor(), -16.0),
        ])

    def update_quick_actions(self, label: str, setup: TabSetup) -> None:
        state = self._quick_action_state.get(label)
        if not state:
            return
        bar, buttons, dispatcher, _scroll, _ = state
        dispatcher.updateHandlers_(setup.handlers)
        for button, action in zip(buttons, setup.actions):
            button.setTitle_(action.title)
            image = self.symbols.symbol(action.symbol, 15.0)
            if image is not None:
                button.setImage_(image)
        self._quick_action_state[label] = (bar, buttons, dispatcher, _scroll, setup)

    def create_button(self, title: str, callback: Callable[[], None], symbol: Optional[str] = None) -> object:
        button = self.AppKit.NSButton.buttonWithTitle_target_action_(title, None, None)
        button.setBezelStyle_(self.AppKit.NSBezelStyleRounded)
        button.setTranslatesAutoresizingMaskIntoConstraints_(False)
        target = self._callback_target_class.alloc().initWithCallback_(callback)
        button.setTarget_(target)
        button.setAction_("invoke:")
        self._callback_targets.append(target)
        if symbol:
            image = self.symbols.symbol(symbol, 15.0)
            if image is not None:
                button.setImage_(image)
                button.setImagePosition_(self.AppKit.NSImageLeft)
        return button

    def select_tab(self, label: str) -> None:
        item = self.tab_items.get(label)
        if item is not None:
            self.tab_view.selectTabViewItem_(item)

    def present_pairing_sheet(self) -> None:
        self._pairing_presenter.present()

    def reveal_profile(self) -> None:
        profile = Path(self.data_provider.profile_path())
        self.AppKit.NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_([
            NSURL.fileURLWithPath_(str(profile))
        ])

    def open_profiles_directory(self) -> None:
        directory = Path(self.data_provider.profile_path()).parent
        self.AppKit.NSWorkspace.sharedWorkspace().openURL_(NSURL.fileURLWithPath_(str(directory)))

    def open_logs_directory(self) -> None:
        logs = Path.home() / "Library" / "Logs" / "Silta"
        logs.mkdir(parents=True, exist_ok=True)
        self.AppKit.NSWorkspace.sharedWorkspace().openURL_(NSURL.fileURLWithPath_(str(logs)))

    def open_bluetooth_preferences(self) -> None:
        url = NSURL.URLWithString_("x-apple.systempreferences:com.apple.Bluetooth")
        if url is not None and not self.AppKit.NSWorkspace.sharedWorkspace().openURL_(url):
            self._notify("Unable to open Bluetooth settings.")

    def export_devices_report(self) -> None:
        sections = self.data_provider.device_sections()
        if not sections:
            self._notify("No devices to export.")
            return
        lines: List[str] = []
        lines.append(f"Silta device inventory · {datetime.now():%Y-%m-%d %H:%M:%S}")
        for section in sections:
            lines.append("")
            lines.append(section.heading)
            for device in section.rows:
                chips = ", ".join(device.detail_chips)
                lines.append(f"- {device.name} [{device.subtitle}] ({chips})")
        destination = Path.home() / "Desktop" / "Silta Devices.txt"
        destination.write_text("\n".join(lines), encoding="utf-8")
        self.AppKit.NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_([
            NSURL.fileURLWithPath_(str(destination))
        ])

    def refresh_devices_tab(self) -> None:
        builder = self.builders.get("Devices")
        if builder is None:
            return
        setup = builder.refresh()
        self.update_quick_actions("Devices", setup)

    def _notify(self, message: str) -> None:
        alert = self.AppKit.NSAlert.alloc().init()
        alert.setMessageText_(message)
        alert.addButtonWithTitle_("OK")
        alert.beginSheetModalForWindow_completionHandler_(self.window, None)


def _animate_fade_in(AppKit, view):
    try:
        view.setAlphaValue_(0.0)
        AppKit.NSAnimationContext.beginGrouping()
        ctx = AppKit.NSAnimationContext.currentContext()
        ctx.setDuration_(0.2)
        view.animator().setAlphaValue_(1.0)
        AppKit.NSAnimationContext.endGrouping()
    except Exception:
        pass


def run() -> None:  # pragma: no cover - UI
    """Launch the standalone Silta Connection Manager window (standalone)."""
    try:
        import AppKit  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "PyObjC AppKit is required for the GUI (pip install 'silta[gui]')"
        ) from exc
    
    # Create app instance
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    
    # Create window with glass effect
    window, content_view, _glass_view = _create_glass_window(AppKit)

    coordinator = ConnectionWindowCoordinator(AppKit, window, content_view)
    coordinator.build()
    _animate_fade_in(AppKit, content_view)

    global _CONTENT_SINGLETON
    _CONTENT_SINGLETON = coordinator
    
    # Set window properties
    window.setReleasedWhenClosed_(False)
    window.makeKeyAndOrderFront_(None)
    window.center()
    
    # Activate app
    app.activateIgnoringOtherApps_(True)
    
    # Run
    app.run()


def open_window_in_current_app() -> None:  # pragma: no cover - UI
    """Open the connection window within an existing NSApplication (menubar)."""
    try:
        import AppKit  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "PyObjC AppKit is required for the GUI (pip install 'silta[gui]')"
        ) from exc

    global _WINDOW_SINGLETON, _CONTENT_SINGLETON
    app = AppKit.NSApplication.sharedApplication()
    if _WINDOW_SINGLETON is not None:
        try:
            _WINDOW_SINGLETON.makeKeyAndOrderFront_(None)
            app.activateIgnoringOtherApps_(True)
            return
        except Exception:
            _WINDOW_SINGLETON = None

    window, content_view, _glass = _create_glass_window(AppKit)
    coordinator = ConnectionWindowCoordinator(AppKit, window, content_view)
    coordinator.build()
    _CONTENT_SINGLETON = coordinator
    _animate_fade_in(AppKit, content_view)
    window.setReleasedWhenClosed_(True)
    window.makeKeyAndOrderFront_(None)
    window.center()
    app.activateIgnoringOtherApps_(True)


if __name__ == "__main__":
    run()
