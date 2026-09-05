"""Security + wiring for MCP OAuth2.

Two things are covered here:
  1. The OAuth2 token endpoint is validated before the operator's client
     secret is sent to it (a manual must not redirect credentials at an
     arbitrary host).
  2. Manual-level OAuth2 is actually applied to the connection (it used to be
     accepted on the call template but never used), and server URLs are
     validated before a connection is dialed.
"""

import asyncio

import aiohttp
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
async def test_insecure_token_url_rejected_before_cache_or_network():
    proto = McpCommunicationProtocol()
    # Seed the cache so a returned token would prove the guard ran too late.
    # The guard must reject the insecure URL before the cache is consulted and
    # before any network request is made.
    auth = _oauth("http://attacker.example/token")
    proto._oauth_tokens[McpCommunicationProtocol._oauth_cache_key(auth)] = {"access_token": "cached"}
    with pytest.raises(ValueError, match="Security error"):
        await proto._handle_oauth2(auth)


@pytest.mark.asyncio
async def test_secure_token_url_passes_the_guard_without_network():
    proto = McpCommunicationProtocol()
    # A pre-seeded token lets us confirm a secure URL passes validation and
    # returns without any network I/O.
    auth = _oauth("https://auth.example.com/token")
    proto._oauth_tokens[McpCommunicationProtocol._oauth_cache_key(auth)] = {"access_token": "cached"}
    token = await proto._handle_oauth2(auth)
    assert token == "cached"


def test_token_endpoint_redirect_is_refused():
    # Redirects are disabled on the token request; a 3xx would be an attempt to
    # bounce the credential-bearing POST elsewhere and must be refused.
    class _Redirect:
        status = 302

    with pytest.raises(aiohttp.ClientError, match="redirect"):
        McpCommunicationProtocol._reject_token_redirect(_Redirect())


def test_token_endpoint_non_redirect_passes():
    class _Ok:
        status = 200

    McpCommunicationProtocol._reject_token_redirect(_Ok())


@pytest.mark.asyncio
async def test_insecure_mcp_server_url_rejected():
    proto = McpCommunicationProtocol()
    template = McpCallTemplate(
        name="m", config=McpConfig(mcpServers={"s": {"url": "http://evil.example/mcp"}})
    )
    with pytest.raises(ValueError, match="Security error"):
        await proto._build_connection_servers(template)


@pytest.mark.asyncio
async def test_loopback_http_server_url_accepted():
    # Loopback HTTP server URLs are allowed for local development, matching the
    # HTTP-family plugins' trust boundary.
    proto = McpCommunicationProtocol()
    template = McpCallTemplate(
        name="m", config=McpConfig(mcpServers={"s": {"url": "http://127.0.0.1:8080/mcp"}})
    )
    servers = await proto._build_connection_servers(template)
    assert servers["s"]["url"] == "http://127.0.0.1:8080/mcp"


@pytest.mark.asyncio
async def test_server_with_own_auth_field_not_overwritten(monkeypatch):
    proto = McpCommunicationProtocol()

    async def fake_token(_auth):
        return "TOK123"

    monkeypatch.setattr(proto, "_handle_oauth2", fake_token)
    template = McpCallTemplate(
        name="m",
        config=McpConfig(
            mcpServers={"s": {"url": "https://mcp.example.com", "auth": {"kind": "custom"}}}
        ),
        auth=_oauth("https://auth.example.com/token"),
    )
    servers = await proto._build_connection_servers(template)
    # A server carrying its own auth keeps it; the manual token is not injected.
    assert "auth_token" not in servers["s"]
    assert servers["s"]["auth"] == {"kind": "custom"}


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
async def test_concurrent_token_fetches_are_coalesced():
    # The token fetch runs outside the client-creation lock, so concurrent
    # first-time callers must share one request rather than each POSTing.
    proto = McpCommunicationProtocol()
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_fetch(auth):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"access_token": "tok"}  # cached by the settle handler, if still current

    proto._fetch_oauth2_token = fake_fetch  # instance attr shadows the method
    auth = _oauth("https://auth.example.com/token")

    tasks = [asyncio.create_task(proto._handle_oauth2(auth)) for _ in range(5)]
    await started.wait()
    release.set()
    results = await asyncio.gather(*tasks)

    assert results == ["tok"] * 5
    assert calls == 1


@pytest.mark.asyncio
async def test_cancelling_one_waiter_does_not_fail_the_others():
    # A waiter awaiting the shared fetch may be cancelled; that must not cancel
    # the shared fetch and fail the remaining waiters.
    proto = McpCommunicationProtocol()
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_fetch(auth):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"access_token": "tok"}  # cached by the settle handler, if still current

    proto._fetch_oauth2_token = fake_fetch
    auth = _oauth("https://auth.example.com/token")

    waiter_a = asyncio.create_task(proto._handle_oauth2(auth))
    await started.wait()  # the shared fetch is running
    waiter_b = asyncio.create_task(proto._handle_oauth2(auth))
    await asyncio.sleep(0)  # let b attach to the shared task

    waiter_a.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_a

    release.set()
    assert await waiter_b == "tok"
    assert calls == 1


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


@pytest.mark.asyncio
async def test_close_drops_cached_tokens():
    # A drain must not leave credentials cached on this shared instance.
    proto = McpCommunicationProtocol()
    auth = _oauth("https://auth.example.com/token")
    proto._oauth_tokens[McpCommunicationProtocol._oauth_cache_key(auth)] = {"access_token": "tok"}
    await proto.close()
    assert proto._oauth_tokens == {}


@pytest.mark.asyncio
async def test_fetch_landing_after_close_does_not_repopulate_cache():
    # close() drops the in-flight entry. The fake fetch deliberately survives the
    # drain's cancel and still LANDS with a value, so the only thing standing
    # between that value and the cache is the identity gate — which must hold.
    proto = McpCommunicationProtocol()
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_fetch(_auth):
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            pass  # survive the drain's cancel so the fetch genuinely lands with a value
        return {"access_token": "late"}

    proto._fetch_oauth2_token = fake_fetch
    auth = _oauth("https://auth.example.com/token")
    waiter = asyncio.create_task(proto._handle_oauth2(auth))
    # Wait until the fetch is genuinely RUNNING (inside its try), not merely
    # scheduled: cancelling a coroutine that has not started throws at its entry
    # and the except never runs, which would test cancellation, not the gate.
    await started.wait()
    assert len(proto._oauth_inflight) == 1

    await proto.close()  # drops the entry; the fetch survives the cancel and lands
    assert await waiter == "late"     # the caller still receives its token...
    assert proto._oauth_tokens == {}  # ...but the fetch was no longer current, so nothing cached
    assert proto._oauth_inflight == {}


def test_require_access_token_rejects_malformed_responses():
    # A 200 without a USABLE access_token is a failed fetch, not a cacheable
    # result. Usable means a non-empty string: a truthy non-string (12345, True)
    # would be injected as an invalid bearer credential on every reuse. The
    # non-string cases are what fail if the isinstance(str) clause is removed.
    for bad in (
        {"token_type": "bearer"},
        ["not", "a", "dict"],
        {"access_token": 12345},
        {"access_token": True},
        {"access_token": ""},
    ):
        with pytest.raises(aiohttp.ClientError, match="access_token"):
            McpCommunicationProtocol._require_access_token(bad)
    assert McpCommunicationProtocol._require_access_token({"access_token": "t"}) == {"access_token": "t"}


@pytest.mark.asyncio
async def test_failed_fetch_is_never_cached_and_can_be_retried():
    # A fetch that fails (including on a malformed body) must leave neither a
    # cache entry nor an in-flight entry behind, so the next call retries.
    proto = McpCommunicationProtocol()

    async def failing_fetch(_auth):
        raise aiohttp.ClientError("OAuth2 token endpoint responded without an access_token")

    proto._fetch_oauth2_token = failing_fetch
    auth = _oauth("https://auth.example.com/token")
    with pytest.raises(aiohttp.ClientError, match="access_token"):
        await proto._handle_oauth2(auth)

    assert proto._oauth_tokens == {}
    assert proto._oauth_inflight == {}
