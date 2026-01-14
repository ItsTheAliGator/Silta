import logging
import socket
import uuid
import json
from typing import Dict, Optional, Callable
from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser, ServiceStateChange, NonUniqueNameException

LOG = logging.getLogger(__name__)

SERVICE_TYPE = "_silta._tcp.local."

class Peer:
    def __init__(self, name: str, address: str, port: int, properties: Dict):
        self.name = name
        self.address = address
        self.port = port
        self.properties = properties
        self.peer_id = properties.get(b'id', b'').decode('utf-8')

    def __repr__(self):
        return f"<Peer {self.name} ({self.address}:{self.port})>"

class DiscoveryService:
    def __init__(self, port: int, peer_name: str, peer_id: Optional[str] = None):
        self.port = port
        self.peer_name = peer_name
        self.peer_id = peer_id or str(uuid.uuid4())
        self._zeroconf = Zeroconf()
        self._service_info: Optional[ServiceInfo] = None
        self._browser: Optional[ServiceBrowser] = None
        self._found_peers: Dict[str, Peer] = {}
        self._on_peer_change: Optional[Callable[[Dict[str, Peer]], None]] = None

    def start_advertising(self):
        """Start advertising this instance on the network."""
        local_ip = self._get_local_ip()
        if not local_ip:
            LOG.error("Could not determine local IP for advertising.")
            return

        desc = {'id': self.peer_id, 'version': '0.1.0'}
        
        self._service_info = ServiceInfo(
            SERVICE_TYPE,
            f"{self.peer_name}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(local_ip)],
            port=self.port,
            properties=desc,
            server=f"{self.peer_id}.local.",
        )
        
        LOG.info(f"Advertising service: {self.peer_name} at {local_ip}:{self.port}")
        try:
            self._zeroconf.register_service(self._service_info)
        except NonUniqueNameException:
            LOG.warning(f"Name {self.peer_name} is taken. Renaming...")
            # Simple retry with ID suffix
            new_name = f"{self.peer_name} ({self.peer_id[:4]})"
            self._service_info = ServiceInfo(
                SERVICE_TYPE,
                f"{new_name}.{SERVICE_TYPE}",
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties=desc,
                server=f"{self.peer_id}.local.",
            )
            # If this fails, we let it crash or retry loop. 
            # For now single retry is robust enough for simple restarts.
            self._zeroconf.register_service(self._service_info)
            self.peer_name = new_name

    def stop_advertising(self):
        """Stop advertising."""
        if self._service_info:
            self._zeroconf.unregister_service(self._service_info)
            self._service_info = None

    def start_browsing(self, on_change: Callable[[Dict[str, Peer]], None]):
        """Start listening for other Silta instances."""
        self._on_peer_change = on_change
        self._browser = ServiceBrowser(self._zeroconf, SERVICE_TYPE, handlers=[self._on_service_state_change])
        LOG.info("Started browsing for peers...")

    def stop_browsing(self):
        """Stop browsing."""
        if self._browser:
            self._browser.cancel()
            self._browser = None

    def shutdown(self):
        """Shutdown all discovery services."""
        self.stop_advertising()
        self.stop_browsing()
        self._zeroconf.close()

    def _on_service_state_change(self, zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange):
        if state_change is ServiceStateChange.Added or state_change is ServiceStateChange.Updated:
            info = zeroconf.get_service_info(service_type, name)
            if info:
                # Ignore self if discovered
                props = info.properties
                pid = props.get(b'id', b'').decode('utf-8')
                if pid == self.peer_id:
                    return

                address = socket.inet_ntoa(info.addresses[0]) if info.addresses else None
                if address:
                    peer = Peer(name.replace(f".{SERVICE_TYPE}", ""), address, info.port, props)
                    self._found_peers[pid] = peer
                    LOG.info(f"Discovered peer: {peer}")
        
        elif state_change is ServiceStateChange.Removed:
            # We need to find which peer corresponds to this name to remove it
            # The name includes the type, e.g. "Ali's Mac._silta._tcp.local."
            # Since we key by ID, we might have to scan values or maintain a reverse map.
            # Simplified: re-scan or just clean up if we can identify.
            # For robustness, we might not remove immediately or we check if we can map name -> id.
            # Ideally Peer object stores the full service name.
             LOG.info(f"Peer removed: {name}")
             # Implementation detail: Removal handling is tricky without mapping name -> ID reliably 
             # if we don't store it. Let's iterate.
             to_remove = []
             for pid, p in self._found_peers.items():
                 if f"{p.name}.{SERVICE_TYPE}" == name:
                     to_remove.append(pid)
             
             for pid in to_remove:
                 del self._found_peers[pid]

        if self._on_peer_change:
            self._on_peer_change(self._found_peers.copy())

    def _get_local_ip(self) -> Optional[str]:
        try:
            # Dummy connection to determine preferred interface
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return None
