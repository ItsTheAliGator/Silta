import logging
import threading
from enum import Enum, auto
from typing import Optional, Callable, Dict, Any

from silta.core.settings import SettingsManager
from silta.core.device_registry import DeviceRegistry
from silta.core.input_orchestrator import InputOrchestrator
from silta.net.discovery import DiscoveryService, Peer
from silta.net.pairing import PairingSession

LOG = logging.getLogger(__name__)

class AppState(Enum):
    IDLE = auto()
    DISCOVERING = auto()
    PAIRING_INITIATOR = auto()
    PAIRING_RECEIVER = auto()
    CONNECTED = auto()

class SessionManager:
    def __init__(self):
        self.settings = SettingsManager(suite_name="group.silta")
        
        # Identity
        self.peer_id = self.settings.peer_id
        if not self.peer_id:
            import uuid
            self.peer_id = str(uuid.uuid4())
            self.settings.peer_id = self.peer_id
            
        self.peer_name = self.settings.get("peer_name", "My Mac")

        # Components
        self.registry = DeviceRegistry()
        self.orchestrator = InputOrchestrator(self.registry)
        self.discovery = DiscoveryService(59873, self.peer_name, self.peer_id)
        
        # State
        self._state = AppState.IDLE
        self._peers: Dict[str, Peer] = {}
        self._active_peer: Optional[Peer] = None
        self._pairing_session: Optional[PairingSession] = None
        
        # Callbacks
        self.on_state_change: Optional[Callable[[AppState], None]] = None
        self.on_peers_update: Optional[Callable[[Dict[str, Peer]], None]] = None
        self.on_pairing_code: Optional[Callable[[str], None]] = None # For UI display
        self.on_pairing_request: Optional[Callable[[str], None]] = None # For UI prompt

    def start(self):
        """Start the session manager (background services)."""
        LOG.info(f"Starting SessionManager as {self.peer_name} ({self.peer_id})")
        self.registry.scan_devices()
        self.set_state(AppState.DISCOVERING)
        self.discovery.start_advertising()
        self.discovery.start_browsing(self._handle_peers_changed)

    def stop(self):
        """Stop all services."""
        self.discovery.shutdown()
        self.orchestrator.stop_control()
        self.set_state(AppState.IDLE)

    def set_state(self, state: AppState):
        if self._state != state:
            LOG.info(f"State change: {self._state} -> {state}")
            self._state = state
            if self.on_state_change:
                self.on_state_change(state)

    def _handle_peers_changed(self, peers: Dict[str, Peer]):
        self._peers = peers
        if self.on_peers_update:
            self.on_peers_update(peers)
        
        # Auto-connect logic could go here if trusted
        
    def initiate_pairing(self, peer_id: str):
        peer = self._peers.get(peer_id)
        if not peer:
            LOG.error("Cannot pair: Peer not found")
            return
        
        self._active_peer = peer
        self.set_state(AppState.PAIRING_INITIATOR)
        
        # In a real implementation we would send a network request to peer
        # telling them "I want to pair".
        # For now, let's assume we generated a code locally
        from silta.net.pairing import generate_otp
        code = generate_otp()
        LOG.info(f"Generated Pairing Code: {code}")
        
        if self.on_pairing_code:
            self.on_pairing_code(code)
            
        self._pairing_session = PairingSession('initiator')
        # TODO: send "pair_request" to peer with my public key? 
        # Wait, the code must be entered on Receiver.
        # So Initiator shows code. Receiver enters code.
        # This implies Initiator waits for Receiver to connect back using the code?
        
    def confirm_pairing_code(self, code: str):
        """Called when user enters code on Receiver side."""
        # Logic to complete pairing
        pass

    # ... Additional logic for handling network events ...
