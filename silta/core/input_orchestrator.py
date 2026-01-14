import logging
from typing import Dict, Optional
from silta.core.device_registry import DeviceRegistry, RegisteredDevice
from silta.hid.backends import easy_switch_via_hidapi # Import specific backend
from silta.client import FlowClient # Wraps event tap
# - Which devices should be forwarded (Software Relay)
# - Which devices should be switched (Hardware Direct)

from silta.core.local_input import LocalInputMonitor
from silta.client import FlowClient # Using FlowClient as the network sender for now


LOG = logging.getLogger(__name__)

class InputOrchestrator:
    def __init__(self, registry: DeviceRegistry):
        self.registry = registry
        self.active_peer_id: Optional[str] = None
        self._software_client: Optional[FlowClient] = None
        self._hardware_active_devices: Dict[str, int] = {} # DeviceID -> OriginalSlot (for return?)

    def set_target_peer(self, peer_id: str, peer_address: str):
        """Set the peer we are controlling."""
        self.active_peer_id = peer_id
        # Initialize software client for relay
        # TODO: Refactor FlowClient to be a pure sender without its own listeners?
        # For now, we inject dependencies or re-instantiate.
        # Ideally we use a lighter Sender class.
        # But FlowClient encapsulates the protocol.
        # Let's assume we can reuse it but disable its internal tapping or hook it up to our monitor.
        
        # Simplified: Create a new client instance configured for this peer
        self._software_client = FlowClient(
            server_host=peer_address,
            server_port=59873,
            token="TODO_TOKEN", # Need to get token from session/settings
            edge=None,
            edge_margin=0,
            edge_delay=0,
            toggle_hotkey="",
            back_hotkey="",
            heartbeat=10.0,
            local_cursor_mode="auto",
            return_margin=10
        )
        # We need to manually start its connection manager but NOT its loop() which blocks.
        # FlowClient.run() blocks. We need async or threaded start.
        self._software_client._start_connection_manager()


    def start_control(self):
        """
        Activate control.
        - For Software devices: Start event capture loop.
        - For Hardware devices: Send Easy-Switch command.
        """
        LOG.info("Starting Input Control...")
        
        devices = self.registry.scan_devices() # Refresh?
        
        software_relay_needed = False
        
        for dev in devices:
            if dev.strategy.type == 'hardware_direct':
                self._switch_hardware_device(dev)
            else:
                software_relay_needed = True

        if software_relay_needed:
            self._start_software_relay()

    def stop_control(self):
        """
        Stop control.
        - Stop software relay.
        - Revert hardware devices (if possible/needed).
        """
        LOG.info("Stopping Input Control...")
        
        self._stop_software_relay()
        self._revert_hardware_devices()

    def _switch_hardware_device(self, dev: RegisteredDevice):
        if not dev.hid_device: return
        LOG.info(f"Switching {dev.name} to Remote Slot via Hardware...")
        
        # TODO: Lookup proper slot from settings (e.g. self.registry.get_slot_mapping(dev.id, peer_id))
        target_slot = 2 
        
        try:
            from silta.capabilities import EasySwitchController
            controller = EasySwitchController.from_device(dev.hid_device)
            if controller:
                controller.switch_slot(target_slot)
            else:
                LOG.warning(f"Device {dev.name} is not a recognized Easy-Switch device.")
                
        except Exception as e:
            LOG.error(f"Failed to switch hardware: {e}")

    def _revert_hardware_devices(self):
        # We can't revert hardware devices easily if we lost connection to them!
        # The Remote Silta instance must send them back.
        pass

    def _start_software_relay(self):
        if self._software_client:
            self._software_client.activate_remote(reason="hybrid_orchestrator")

    def _stop_software_relay(self):
        if self._software_client:
            self._software_client.deactivate_remote(reason="hybrid_orchestrator_stop")
