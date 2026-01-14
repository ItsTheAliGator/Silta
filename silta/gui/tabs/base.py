from __future__ import annotations

from typing import TYPE_CHECKING, List, Callable, Tuple, Any, Sequence, Optional
from dataclasses import dataclass

if TYPE_CHECKING:
    from silta.gui.data import WindowDataProvider
    from silta.gui.views import CardFactory, SymbolProvider

@dataclass
class QuickAction:
    action_id: str
    title: str
    symbol: str

@dataclass
class TabSetup:
    actions: List[QuickAction]
    handlers: List[Callable[[], None]]

class TabBuilder:
    def __init__(self, coordinator: Any) -> None:
        self._coordinator = coordinator
        self._AppKit = coordinator.AppKit
        self._data: WindowDataProvider = coordinator.data_provider
        self._cards: CardFactory = coordinator.card_factory
        self._symbols: SymbolProvider = coordinator.symbols

    def render(self, parent_view: object) -> Tuple[TabSetup, object]:
        raise NotImplementedError

    def refresh(self) -> TabSetup:
        # Default no-op
        return TabSetup([], [])

class StackTabBuilder(TabBuilder):
    def __init__(self, coordinator: Any) -> None:
        super().__init__(coordinator)
        self._stack: Optional[object] = None

    def render(self, parent_view: object) -> Tuple[TabSetup, object]:
        AppKit = self._AppKit
        
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(parent_view.bounds())
        scroll.setTranslatesAutoresizingMaskIntoConstraints_(False)
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(0)  # NSNoBorder
        scroll.setHasVerticalScroller_(True)
        
        content = AppKit.NSView.alloc().initWithFrame_(parent_view.bounds())
        content.setTranslatesAutoresizingMaskIntoConstraints_(False)
        scroll.setDocumentView_(content)
        
        parent_view.addSubview_(scroll)
        AppKit.NSLayoutConstraint.activateConstraints_([
            scroll.leadingAnchor().constraintEqualToAnchor_(parent_view.leadingAnchor()),
            scroll.trailingAnchor().constraintEqualToAnchor_(parent_view.trailingAnchor()),
            scroll.topAnchor().constraintEqualToAnchor_(parent_view.topAnchor()),
            # Note: scroll.bottomAnchor is constrained by the coordinator (to the toolbar).
        ])
        
        stack = AppKit.NSStackView.stackViewWithViews_([])
        stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        stack.setSpacing_(24.0)
        stack.setEdgeInsets_((24, 24, 24, 24))
        stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        content.addSubview_(stack)
        
        # Pin stack to content edges
        AppKit.NSLayoutConstraint.activateConstraints_([
            stack.leadingAnchor().constraintEqualToAnchor_(content.leadingAnchor()),
            stack.trailingAnchor().constraintEqualToAnchor_(content.trailingAnchor()),
            stack.topAnchor().constraintEqualToAnchor_(content.topAnchor()),
            # Tight fit for vertical scrolling
            stack.bottomAnchor().constraintEqualToAnchor_(content.bottomAnchor()),
            # Also ensure width matches
            stack.widthAnchor().constraintEqualToAnchor_(content.widthAnchor()),
        ])
        
        self._stack = stack
        return self._populate(), scroll

    def _populate(self) -> TabSetup:
        raise NotImplementedError
