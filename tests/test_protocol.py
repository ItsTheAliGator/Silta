import hmac
import hashlib

import pytest

from flowlite.protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    build_client_hello,
    build_server_welcome,
    validate_client_hello,
    validate_server_welcome,
)


def test_build_client_hello_hmac_authentication() -> None:
    token = "supersecret"
    hello = build_client_hello(token)
    assert hello["version"] == PROTOCOL_VERSION
    nonce = hello["nonce"]
    assert isinstance(nonce, str) and len(nonce) == 32
    expected = hmac.new(token.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256).hexdigest()
    assert hello["auth"] == expected
    # Server-side verification should pass
    validate_client_hello(dict(hello), token)


def test_validate_client_hello_requires_auth_when_token_expected() -> None:
    hello = build_client_hello(None)
    hello["nonce"] = "deadbeef"
    hello.pop("auth", None)
    with pytest.raises(ProtocolError):
        validate_client_hello(hello, "secret")


def test_validate_server_welcome_version_guard() -> None:
    welcome = build_server_welcome()
    validate_server_welcome(welcome)
    with pytest.raises(ProtocolError):
        validate_server_welcome({"type": "welcome", "version": PROTOCOL_VERSION + 1})
