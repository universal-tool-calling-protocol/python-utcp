"""Security + wiring for MCP OAuth2.

Two things are covered here:
  1. The OAuth2 token endpoint is validated before the operator's client
     secret is sent to it (a manual must not redirect credentials at an
     arbitrary host).
  2. Manual-level OAuth2 is actually applied to the connection (it used to be
     accepted on the call template but never used), and server URLs are
     validated before a connection is dialed.
"""

import pytest

from utcp.data.auth_implementations import OAuth2Auth
from utcp_mcp.mcp_call_template import McpCallTemplate, McpConfig
from utcp_mcp.mcp_communication_protocol import McpCommunicationProtocol


def _oauth(token_url: str) -> OAuth2Auth:
    return OAuth2Auth(
        auth_type="oauth2",
        token_url=token_url,
        client_id="id",
        client_secret="secret",
        scope="",
    )


@pytest.mark.asyncio
async def test_insecure_token_url_rejected_before_any_request():
    proto = McpCommunicationProtocol()
    with pytest.raises(ValueError, match="Security error"):
        await proto._handle_oauth2(_oauth("http://attacker.example/token"))


@pytest.mark.asyncio
async def test_secure_token_url_passes_the_guard():
    proto = McpCommunicationProtocol()
    # Validation passes for a loopback token URL; the fetch then fails with a
    # connection error, which must NOT be the security-guard message.
    with pytest.raises(Exception) as excinfo:
        await proto._handle_oauth2(_oauth("http://127.0.0.1:1/token"))
    assert "Security error" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_insecure_mcp_server_url_rejected():
    proto = McpCommunicationProtocol()
    template = McpCallTemplate(
        name="m", config=McpConfig(mcpServers={"s": {"url": "http://evil.example/mcp"}})
    )
    with pytest.raises(ValueError, match="Security error"):
        await proto._build_connection_servers(template)


@pytest.mark.asyncio
async def test_oauth_token_injected_for_http_server(monkeypatch):
    proto = McpCommunicationProtocol()

    async def fake_token(_auth):
        return "TOK123"

    monkeypatch.setattr(proto, "_handle_oauth2", fake_token)
    template = McpCallTemplate(
        name="m",
        config=McpConfig(mcpServers={"s": {"url": "https://mcp.example.com"}}),
        auth=_oauth("https://auth.example.com/token"),
    )
    servers = await proto._build_connection_servers(template)
    # mcp-use turns auth_token into an Authorization: Bearer header.
    assert servers["s"]["auth_token"] == "TOK123"
    # The caller's template is never mutated (and the token never leaks into
    # the value the client is keyed by).
    assert "auth_token" not in template.config.mcpServers["s"]


@pytest.mark.asyncio
async def test_existing_server_credentials_not_overwritten(monkeypatch):
    proto = McpCommunicationProtocol()

    async def fake_token(_auth):
        return "TOK123"

    monkeypatch.setattr(proto, "_handle_oauth2", fake_token)
    template = McpCallTemplate(
        name="m",
        config=McpConfig(
            mcpServers={"s": {"url": "https://mcp.example.com", "auth_token": "own"}}
        ),
        auth=_oauth("https://auth.example.com/token"),
    )
    servers = await proto._build_connection_servers(template)
    assert servers["s"]["auth_token"] == "own"


@pytest.mark.asyncio
async def test_manuals_with_same_servers_but_different_auth_get_distinct_keys():
    a = McpCallTemplate(
        name="m",
        config=McpConfig(mcpServers={"s": {"url": "https://mcp.example.com"}}),
        auth=_oauth("https://auth-a.example.com/token"),
    )
    b = McpCallTemplate(
        name="m",
        config=McpConfig(mcpServers={"s": {"url": "https://mcp.example.com"}}),
        auth=_oauth("https://auth-b.example.com/token"),
    )
    assert McpCommunicationProtocol._config_key(a) != McpCommunicationProtocol._config_key(b)
