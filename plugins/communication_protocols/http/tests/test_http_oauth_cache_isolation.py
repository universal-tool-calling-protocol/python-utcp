"""OAuth2 token caches are isolated per credential configuration.

Each HTTP-family protocol keys its token cache by ``OAuth2Auth.cache_key``,
so two templates that share a ``client_id`` but differ in issuer, secret or
scope never receive each other's tokens. Network-free: the cache is seeded
directly, and the second configuration is only checked for absence.
"""

import pytest

from utcp.data.auth_implementations import OAuth2Auth
from utcp_http.http_communication_protocol import HttpCommunicationProtocol
from utcp_http.sse_communication_protocol import SseCommunicationProtocol
from utcp_http.streamable_http_communication_protocol import StreamableHttpCommunicationProtocol


def _auth(token_url: str) -> OAuth2Auth:
    return OAuth2Auth(
        auth_type="oauth2", token_url=token_url, client_id="shared", client_secret="s", scope=""
    )


@pytest.mark.parametrize(
    "protocol_class",
    [HttpCommunicationProtocol, SseCommunicationProtocol, StreamableHttpCommunicationProtocol],
)
@pytest.mark.asyncio
async def test_token_cache_is_isolated_per_credential_configuration(protocol_class):
    proto = protocol_class()
    a = _auth("https://issuer-a.example/token")
    b = _auth("https://issuer-b.example/token")  # same client_id, different issuer

    proto._oauth_tokens[a.cache_key()] = {"access_token": "token-for-a"}

    # A is served from the cache (proves the key is what the lookup uses)...
    assert await proto._handle_oauth2(a) == "token-for-a"
    # ...and B, sharing only the client_id, has no entry and so can never be
    # handed A's token.
    assert b.cache_key() not in proto._oauth_tokens
