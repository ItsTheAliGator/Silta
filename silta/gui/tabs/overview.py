from __future__ import annotations
from .base import TabBuilder, TabSetup, QuickAction
from silta.gui.peer_browser import PeerBrowserView
from silta.gui.views import _make_label

class OverviewTabBuilder(TabBuilder):
    def render(self, parent_view: object) -> tuple[TabSetup, object]:
        coordinator = self._coordinator
        AppKit = coordinator.AppKit
        
        # Use PeerBrowserView directly
        browser = PeerBrowserView(coordinator)
        container = browser.render(parent_view)
        
        # Start listening
        browser.start_discovery()
        
        actions = [
            QuickAction("pair", "Pair", "bolt.horizontal.circle"),
            QuickAction("refresh", "Refresh", "arrow.clockwise"),
        ]
        
        def refresh():
            # Trigger refresh?
            # SessionManager keeps scanning. Maybe clear list?
            pass
            
        handlers = [
            lambda: coordinator.present_pairing_sheet(),
            refresh
        ]
        
        return TabSetup(actions=actions, handlers=handlers), container
