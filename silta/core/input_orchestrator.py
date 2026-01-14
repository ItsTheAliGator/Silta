import logging
from typing import Dict, Optional
from silta.core.device_registry import DeviceRegistry, RegisteredDevice
from silta.hid.backends import easy_switch_via_hidapi # Import specific backend
from silta.client import FlowClient # Wraps event tap
# TODO: We need a way to control specific devices.
# InputOrchestrator coordinates:
# - Active Peer (Target)
# - Which devices should be forwarded (Software Relay)
# - Which devices should be switched (Hardware Direct)

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
        # Port hardcoded or discoverable? discovery service provides port.
        # For now assuming standard port or passed in.
        # self._software_client = FlowClient(peer_address, 59873) # TODO: dynamic port

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
        # TODO: Lookup proper slot for this peer from configuration
        target_slot = 2 # Placeholder: User must map this!
        
        try:
            # We need to know which backend to use.
            # Assuming backend selection logic exists or we use generic.
            # Warning: easy_switch_via_hidapi might need context.
            # For now simplified call.
            # NOTE: this is "fire and forget". We lose control of the mouse!
            # To get it back, the user must switch it back on the other computer,
            # OR we rely on the other computer running Silta to switch it back??
            # Actually, "Hardware Direct" usually means we lose it until we move edge on remote.
            pass
        except Exception as e:
            LOG.error(f"Failed to switch hardware: {e}")

    def _revert_hardware_devices(self):
        # We can't revert hardware devices easily if we lost connection to them!
        # The Remote Silta instance must send them back.
        pass

    def _start_software_relay(self):
        if self._software_client:
            # self._software_client.start()
            pass

    def _stop_software_relay(self):
        if self._software_client:
            # self._software_client.stop()
            pass
