import json
import os
import sys
from typing import Any, Optional, Dict
from silta.utils import LOG

class SettingsManager:
    def __init__(self, suite_name: Optional[str] = None):
        self.suite_name = suite_name
        self._defaults = None
        
        if sys.platform == "darwin":
            try:
                from Foundation import NSUserDefaults
                if suite_name:
                    self._defaults = NSUserDefaults.alloc().initWithSuiteName_(suite_name)
                else:
                    self._defaults = NSUserDefaults.standardUserDefaults()
            except ImportError:
                LOG.warning("NSUserDefaults unavailable; falling back to file/memory")
        
        # Fallback storage
        self._fallback_path = os.path.expanduser("~/.silta_config.json")
        self._cache: Dict[str, Any] = {}
        if not self._defaults and os.path.exists(self._fallback_path):
            try:
                with open(self._fallback_path, 'r') as f:
                    self._cache = json.load(f)
            except Exception: pass

    def get(self, key: str, default: Any = None) -> Any:
        if self._defaults:
            val = self._defaults.objectForKey_(key)
            if val is None:
                return default
            return val
        return self._cache.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if self._defaults:
            self._defaults.setObject_forKey_(value, key)
            # synchronize? typically auto
        else:
            self._cache[key] = value
            self._save_fallback()

    def _save_fallback(self):
        try:
            with open(self._fallback_path, 'w') as f:
                json.dump(self._cache, f)
        except Exception as e:
            LOG.error(f"Failed to save settings: {e}")

    # Typed accessors
    @property
    def peer_id(self) -> Optional[str]:
        return self.get("peer_id")

    @peer_id.setter
    def peer_id(self, val: str):
        self.set("peer_id", val)

    @property
    def trusted_peers(self) -> Dict[str, str]:
        # Stored as JSON string or dict? NSUserDefaults supports dicts.
        val = self.get("trusted_peers", {})
        if isinstance(val, dict): return val
        return {} # Handle types

    def add_trusted_peer(self, peer_id: str, key: str):
        peers = self.trusted_peers.copy()
        peers[peer_id] = key
        self.set("trusted_peers", peers)
