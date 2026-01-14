from __future__ import annotations

"""Pairing helpers: save/load edge profiles and test server connectivity.

This module provides a tiny persistence layer for Flow edge profiles and a
connection self-test using Silta's handshake protocol. It intentionally does
not launch the client; it only prepares configuration that the client can use.
"""

import json
import os
import socket
from typing import Dict, Optional, Tuple

from .protocol import build_client_hello, validate_server_welcome, ProtocolError
from .utils import LOG


def _app_support_dir() -> str:
    base = os.path.expanduser("~/Library/Application Support/Silta")
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        pass
    return base


def default_profile_path() -> str:
    return os.path.join(_app_support_dir(), "edge_profiles.json")


def load_profiles(path: Optional[str] = None) -> Dict[str, Tuple[str, int, Optional[str]]]:
    dest = path or default_profile_path()
    try:
        with open(dest, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        LOG.debug("Unable to read profiles: %s", exc)
        return {}
    profiles: Dict[str, Tuple[str, int, Optional[str]]] = {}
    if isinstance(raw, dict):
        for edge, cfg in raw.items():
            if not isinstance(edge, str) or not isinstance(cfg, dict):
                continue
            host = cfg.get("host") or cfg.get("server")
            port = cfg.get("port", 59873)
            token = cfg.get("auth_token") or cfg.get("token")
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = 59873
            if isinstance(host, str):
                profiles[edge.lower()] = (host, port, token if isinstance(token, str) else None)
    return profiles


def save_profile(edge: str, host: str, port: int, token: Optional[str], path: Optional[str] = None) -> str:
    edge = edge.lower()
    dest = path or default_profile_path()
    try:
        with open(dest, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    raw[edge] = {"host": host, "port": int(port), "auth_token": token}
    # Also set as default if not present
    raw.setdefault("default", {"host": host, "port": int(port), "auth_token": token})
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2)
    os.replace(tmp, dest)
    return dest


def test_connection(host: str, port: int, token: Optional[str], timeout: float = 5.0) -> Tuple[bool, str]:
    """Attempt a handshake against a Silta server."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as sock:
            reader = sock.makefile("rb")
            writer = sock.makefile("wb")
            hello = build_client_hello(token)
            writer.write((json.dumps(hello) + "\n").encode("utf-8"))
            writer.flush()
            line = reader.readline()
            if not line:
                return False, "Server closed connection"
            try:
                reply = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                return False, "Malformed reply from server"
            try:
                validate_server_welcome(reply)
            except ProtocolError as exc:
                return False, f"Handshake failed: {exc}"
            return True, "Handshake OK"
    except OSError as exc:
        return False, f"Socket error: {exc}"
