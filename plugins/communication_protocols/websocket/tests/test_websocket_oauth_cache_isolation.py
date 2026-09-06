"""OAuth2 token cache is isolated per credential configuration.

The token cache is keyed by ``OAuth2Auth.cache_key``, so two templates that
share a ``client_id`` but differ in issuer, secret or scope never receive each
other's tokens. Network-free: the cache is seeded directly, and the second
configuration is only checked for absence.
"""

import pytest

from utcp.data.auth_implementations import OAuth2Auth
from utcp_websocket.websocket_communication_protocol import WebSocketCommunicationProtocol


def _auth(token_url: str) -> OAuth2Auth:
    return OAuth2Auth(
        auth_type="oauth2", token_url=token_url, client_id="shared", client_secret="s", scope=""
    )


@pytest.mark.asyncio
async def test_token_cache_is_isolated_per_credential_configuration():
    proto = WebSocketCommunicationProtocol()
    a = _auth("https://issuer-a.example/token")
    b = _auth("https://issuer-b.example/token")  # same client_id, different issuer

    proto._oauth_tokens[a.cache_key()] = {"access_token": "token-for-a"}

    assert await proto._handle_oauth2(a) == "token-for-a"
    assert b.cache_key() not in proto._oauth_tokens
