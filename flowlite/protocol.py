from __future__ import annotations

import hmac
import hashlib
import secrets
from typing import Any, Dict, Optional


PROTOCOL_VERSION = 2


class ProtocolError(RuntimeError):
    """Raised when protocol expectations are not met."""


def _compute_auth(token: str, nonce: str) -> str:
    digest = hmac.new(token.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


def build_client_hello(token: Optional[str]) -> Dict[str, Any]:
    nonce = secrets.token_hex(16)
    payload: Dict[str, Any] = {
        "type": "hello",
        "client": "flowlite",
        "version": PROTOCOL_VERSION,
        "nonce": nonce,
    }
    if token:
        payload["auth"] = _compute_auth(token, nonce)
    return payload


def build_server_welcome() -> Dict[str, Any]:
    return {"type": "welcome", "server": "flowlite", "version": PROTOCOL_VERSION}


def validate_server_welcome(welcome: Dict[str, Any]) -> None:
    if welcome.get("type") != "welcome":
        raise ProtocolError("Unexpected handshake response from server")
    try:
        version = int(welcome.get("version"))
    except (TypeError, ValueError):
        raise ProtocolError("Server handshake did not include a valid version") from None
    if version != PROTOCOL_VERSION:
        raise ProtocolError(
            f"Protocol version mismatch. Client={PROTOCOL_VERSION} Server={version}"
        )


def validate_client_hello(hello: Dict[str, Any], token: Optional[str]) -> str:
    if hello.get("type") != "hello":
        raise ProtocolError("Missing hello message from client")
    try:
        version = int(hello.get("version"))
    except (TypeError, ValueError):
        raise ProtocolError("Client handshake did not include a valid version") from None
    if version != PROTOCOL_VERSION:
        raise ProtocolError(
            f"Protocol version mismatch. Server={PROTOCOL_VERSION} Client={version}"
        )

    nonce = hello.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        raise ProtocolError("Client handshake missing nonce")

    if token:
        auth = hello.get("auth")
        if not isinstance(auth, str):
            raise ProtocolError("Client handshake missing auth token")
        expected = _compute_auth(token, nonce)
        if not hmac.compare_digest(auth, expected):
            raise ProtocolError("Client authentication failed")

    return nonce
