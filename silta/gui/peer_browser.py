from __future__ import annotations

import threading
from typing import Dict, Any, Optional, Callable, List
from silta.net.discovery import DiscoveryService, Peer
from silta.gui.views import _make_label, _make_body_text
from silta.gui.data import WindowDataProvider

class PeerBrowserView:
    def __init__(self, coordinator: Any) -> None:
        self.coordinator = coordinator
        self.AppKit = coordinator.AppKit
        self.peers: Dict[str, Peer] = {}
        self.discovery: Optional[DiscoveryService] = None
        self._container = None
        self._stack = None
        self._peer_views: Dict[str, Any] = {}
        
    def start_discovery(self) -> None:
        mgr = self.coordinator.session_manager
        if not mgr: return
        
        # Subscribe to updates
        self._update_list(mgr._peers) # Initial
        mgr.on_peers_update = self._on_peers_changed
        
        # Ensure discovery is running?
        # SessionManager.start() should be called by window coordinator.

    def stop_discovery(self) -> None:
        if self.coordinator.session_manager:
            self.coordinator.session_manager.on_peers_update = None

    def render(self, parent_view: object) -> object:
        AppKit = self.AppKit
        
        container = AppKit.NSView.alloc().initWithFrame_(parent_view.bounds())
        container.setTranslatesAutoresizingMaskIntoConstraints_(False)
        parent_view.addSubview_(container)
        
        AppKit.NSLayoutConstraint.activateConstraints_([
            container.leadingAnchor().constraintEqualToAnchor_(parent_view.leadingAnchor()),
            container.trailingAnchor().constraintEqualToAnchor_(parent_view.trailingAnchor()),
            container.topAnchor().constraintEqualToAnchor_(parent_view.topAnchor()),
            container.bottomAnchor().constraintEqualToAnchor_(parent_view.bottomAnchor()),
        ])
        
        # Title
        title = _make_label(AppKit, "Nearby Devices", 24.0, AppKit.NSFontWeightBold)
        container.addSubview_(title)
        
        AppKit.NSLayoutConstraint.activateConstraints_([
            title.centerXAnchor().constraintEqualToAnchor_(container.centerXAnchor()),
            title.topAnchor().constraintEqualToAnchor_constant_(container.topAnchor(), 40.0),
        ])
        
        # Scroll View for Peers
        scroll = AppKit.NSScrollView.alloc().init()
        scroll.setTranslatesAutoresizingMaskIntoConstraints_(False)
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(0)
        container.addSubview_(scroll)
        
        AppKit.NSLayoutConstraint.activateConstraints_([
            scroll.topAnchor().constraintEqualToAnchor_constant_(title.bottomAnchor(), 30.0),
            scroll.leadingAnchor().constraintEqualToAnchor_constant_(container.leadingAnchor(), 40.0),
            scroll.trailingAnchor().constraintEqualToAnchor_constant_(container.trailingAnchor(), -40.0),
            scroll.bottomAnchor().constraintEqualToAnchor_constant_(container.bottomAnchor(), -40.0),
        ])
        
        content = AppKit.NSView.alloc().init()
        content.setTranslatesAutoresizingMaskIntoConstraints_(False)
        scroll.setDocumentView_(content)
        
        stack = AppKit.NSStackView.stackViewWithViews_([])
        stack.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationVertical)
        stack.setSpacing_(16.0)
        stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        content.addSubview_(stack)
        
        AppKit.NSLayoutConstraint.activateConstraints_([
            stack.topAnchor().constraintEqualToAnchor_(content.topAnchor()),
            stack.leadingAnchor().constraintEqualToAnchor_(content.leadingAnchor()),
            stack.trailingAnchor().constraintEqualToAnchor_(content.trailingAnchor()),
            stack.widthAnchor().constraintEqualToAnchor_(scroll.widthAnchor()), # Full width
            # Stack bottom defines content bottom
            stack.bottomAnchor().constraintEqualToAnchor_(content.bottomAnchor()),
        ])
        
        self._container = container
        self._stack = stack
        
        # Initial empty state?
        return container

    def _on_peers_changed(self, peers: Dict[str, Peer]) -> None:
        # Dispatch to main thread updates
        def update():
            self._update_list(peers)
        
        if hasattr(self.AppKit, 'NSThread'):
             if self.AppKit.NSThread.isMainThread():
                 update()
             else:
                 self.AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(update)
        else:
             # Fallback if AppKit logic varies slightly or mocking
             pass

    def _update_list(self, new_peers: Dict[str, Peer]) -> None:
        AppKit = self.AppKit
        current_ids = set(self._peer_views.keys())
        new_ids = set(new_peers.keys())
        
        # Remove old
        for pid in current_ids - new_ids:
            view = self._peer_views.pop(pid)
            view.removeFromSuperview()
            
        # Add new
        for pid in new_ids - current_ids:
            peer = new_peers[pid]
            row = self._create_peer_row(peer)
            self._peer_views[pid] = row
            self._stack.addArrangedSubview_(row)
            
        self.peers = new_peers
        
    def _create_peer_row(self, peer: Peer) -> object:
        AppKit = self.AppKit
        row = AppKit.NSView.alloc().init()
        row.setTranslatesAutoresizingMaskIntoConstraints_(False)
        row.setWantsLayer_(True)
        if row.layer():
            row.layer().setBackgroundColor_(AppKit.NSColor.controlBackgroundColor().colorWithAlphaComponent_(0.6).CGColor())
            row.layer().setCornerRadius_(12.0)
            
        row.heightAnchor().constraintEqualToConstant_(60.0).setActive_(True)
        
        # Icon
        icon_img = self.coordinator.symbols.symbol("laptopcomputer", 24.0)
        icon = AppKit.NSImageView.imageViewWithImage_(icon_img)
        icon.setTranslatesAutoresizingMaskIntoConstraints_(False)
        icon.setContentTintColor_(AppKit.NSColor.secondaryLabelColor())
        row.addSubview_(icon)
        
        # Name
        name_lbl = _make_label(AppKit, peer.name, 15.0, AppKit.NSFontWeightMedium)
        row.addSubview_(name_lbl)
        
        # Connect Button
        btn = AppKit.NSButton.buttonWithTitle_target_action_("Connect", None, None)
        btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        btn.setTranslatesAutoresizingMaskIntoConstraints_(False)
        
        # Clean way to handle action? Tag or Closure wrapper?
        # Re-using callback target logic from coordinator if possible or creating new one.
        # For prototype, we'll skip the target binding logic unless we import helper.
        # Assuming coordinator can bind.
        
        row.addSubview_(btn)
        
        AppKit.NSLayoutConstraint.activateConstraints_([
            icon.leadingAnchor().constraintEqualToAnchor_constant_(row.leadingAnchor(), 16.0),
            icon.centerYAnchor().constraintEqualToAnchor_(row.centerYAnchor()),
            
            name_lbl.leadingAnchor().constraintEqualToAnchor_constant_(icon.trailingAnchor(), 16.0),
            name_lbl.centerYAnchor().constraintEqualToAnchor_(row.centerYAnchor()),
            
            btn.trailingAnchor().constraintEqualToAnchor_constant_(row.trailingAnchor(), -16.0),
            btn.centerYAnchor().constraintEqualToAnchor_(row.centerYAnchor()),
        ])
        
        return row
