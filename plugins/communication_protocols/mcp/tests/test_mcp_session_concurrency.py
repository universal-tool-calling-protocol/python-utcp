"""Concurrent session creation must dial once, not spawn (and leak) duplicates.

``_get_or_create_session`` coalesces concurrent first-time creations for the
same (configuration, server) into a single shared task, shielded so one
waiter's cancellation can't cancel the creation for the others.
"""

import asyncio

import pytest

from utcp_mcp.mcp_call_template import McpCallTemplate, McpConfig
from utcp_mcp.mcp_communication_protocol import McpCommunicationProtocol


def _template() -> McpCallTemplate:
    return McpCallTemplate(name="m", config=McpConfig(mcpServers={"s": {"command": "true"}}))


class _NoSessionClient:
    """Stands in for an MCPClient that has no session yet."""

    def get_session(self, name):
        raise ValueError("no session")


def _stub_client(proto: McpCommunicationProtocol, monkeypatch):
    # One shared instance, as the real _ensure_mcp_client returns the same client
    # for the same configuration; in-flight creations are keyed by client identity.
    client = _NoSessionClient()

    async def fake_ensure(_tmpl):
        return client

    monkeypatch.setattr(proto, "_ensure_mcp_client", fake_ensure)


@pytest.mark.asyncio
async def test_concurrent_session_creation_is_coalesced(monkeypatch):
    proto = McpCommunicationProtocol()
    _stub_client(proto, monkeypatch)

    creations = 0
    release = asyncio.Event()

    async def fake_create(server_name, client, tmpl):
        nonlocal creations
        creations += 1
        await release.wait()
        return f"session-{server_name}"

    monkeypatch.setattr(proto, "_create_session", fake_create)

    tmpl = _template()
    tasks = [asyncio.create_task(proto._get_or_create_session("s", tmpl)) for _ in range(5)]
    await asyncio.sleep(0)  # let every caller attach to the shared creation
    release.set()
    results = await asyncio.gather(*tasks)

    assert results == ["session-s"] * 5
    assert creations == 1
    assert proto._session_creations == {}  # slot cleared on settle


@pytest.mark.asyncio
async def test_cancelling_one_session_waiter_does_not_fail_the_others(monkeypatch):
    proto = McpCommunicationProtocol()
    _stub_client(proto, monkeypatch)

    creations = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_create(server_name, client, tmpl):
        nonlocal creations
        creations += 1
        started.set()
        await release.wait()
        return f"session-{server_name}"

    monkeypatch.setattr(proto, "_create_session", fake_create)

    tmpl = _template()
    waiter_a = asyncio.create_task(proto._get_or_create_session("s", tmpl))
    await started.wait()
    waiter_b = asyncio.create_task(proto._get_or_create_session("s", tmpl))
    await asyncio.sleep(0)

    waiter_a.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_a

    release.set()
    assert await waiter_b == "session-s"
    assert creations == 1
