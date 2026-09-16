"""Security tests for the GraphQL communication protocol (utcp-gql).

Pin the fixes for GHSA-ppx3-28rw-8fpf (the original CVE-2026-44661
URL hardening missed this plugin) and the OAuth2 / redirect halves
of GHSA-8cp3-qxj6-px34 / GHSA-9qhg-99ww-9mqc.
"""

import pytest

from utcp.data.auth_implementations.oauth2_auth import OAuth2Auth
from utcp_gql._security import (
    ensure_secure_url,
    is_secure_url,
)
from utcp_gql.gql_call_template import GraphQLCallTemplate
from utcp_gql.gql_communication_protocol import GraphQLCommunicationProtocol


# ---------------------------------------------------------------------------
# Hostname-based validator must reject the same prefix bypass as utcp-http.
# ---------------------------------------------------------------------------


class TestUrlValidatorRejectsPrefixBypass:
    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost.evil.com/graphql",
            "http://127.0.0.1.attacker.example/graphql",
            "http://169.254.169.254/graphql",
            "http://10.0.0.5/graphql",
            "http://internal.service.local/graphql",
            "http://example.com/graphql",
        ],
    )
    def test_bypass_url_rejected(self, url: str) -> None:
        assert is_secure_url(url) is False
        with pytest.raises(ValueError, match="HTTPS or be a literal loopback"):
            ensure_secure_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://api.example.com/graphql",
            "http://localhost/graphql",
            "http://127.0.0.1:9090/graphql",
            "http://[::1]:9090/graphql",
        ],
    )
    def test_legitimate_url_accepted(self, url: str) -> None:
        assert is_secure_url(url) is True
        ensure_secure_url(url)  # must not raise


# ---------------------------------------------------------------------------
# register_manual + call_tool: URL validation is now hostname-based.
# ---------------------------------------------------------------------------


class TestRegisterAndCallRejectBypass:
    @pytest.mark.asyncio
    async def test_register_manual_rejects_prefix_bypass(self) -> None:
        proto = GraphQLCommunicationProtocol()
        tpl = GraphQLCallTemplate(
            name="evil",
            url="http://127.0.0.1.attacker.example/graphql",
        )
        # The validator runs before register_manual's try/except so the
        # ValueError propagates rather than being captured in the
        # result.
        with pytest.raises(ValueError, match="HTTPS or be a literal loopback"):
            await proto.register_manual(None, tpl)

    @pytest.mark.asyncio
    async def test_call_tool_rejects_prefix_bypass(self) -> None:
        proto = GraphQLCommunicationProtocol()
        tpl = GraphQLCallTemplate(
            name="evil",
            url="http://localhost.evil.com/graphql",
        )
        with pytest.raises(ValueError, match="HTTPS or be a literal loopback"):
            await proto.call_tool(None, "x", {}, tpl)


# ---------------------------------------------------------------------------
# OAuth2 token URL is validated before credential bytes leave the process.
# ---------------------------------------------------------------------------


class TestOAuth2TokenUrlValidation:
    @pytest.mark.asyncio
    async def test_internal_token_url_rejected(self) -> None:
        proto = GraphQLCommunicationProtocol()
        auth = OAuth2Auth(
            token_url="http://169.254.169.254/token",
            client_id="victim-id",
            client_secret="victim-secret",
        )
        with pytest.raises(ValueError, match="OAuth2 token URL"):
            await proto._handle_oauth2(auth)

    @pytest.mark.asyncio
    async def test_plain_http_non_loopback_token_url_rejected(self) -> None:
        proto = GraphQLCommunicationProtocol()
        auth = OAuth2Auth(
            token_url="http://attacker.example/token",
            client_id="victim-id",
            client_secret="victim-secret",
        )
        with pytest.raises(ValueError, match="OAuth2 token URL"):
            await proto._handle_oauth2(auth)


# ---------------------------------------------------------------------------
# Mirror of utcp_http: loopback in every spelling the resolver accepts, and a
# redirect never enters loopback from a non-loopback origin.
# ---------------------------------------------------------------------------

import pytest as _pytest
from utcp_gql._security import is_loopback_url as _is_loopback_url, safe_request_with_redirects as _safe_request_with_redirects


@_pytest.mark.parametrize(
    "url",
    [
        "https://127.1/x",           # shorthand: inet_aton fills the middle octets
        "https://2130706433/x",      # 127.0.0.1 as a single integer
        "https://0177.0.0.1/x",      # octal
        "https://0x7f000001/x",      # hex
        "https://127.0.0.1./x",      # absolute-name form (trailing dot)
        "https://localhost./x",
        "https://0.0.0.0/x",         # wildcard routes to the local host
        "https://[::ffff:127.0.0.1]/x",
    ],
)
def test_loopback_is_recognised_in_every_resolver_spelling(url):
    assert _is_loopback_url(url)


@_pytest.mark.parametrize("url", ["https://localhost.evil.com/x", "https://127.0.0.1.attacker.example/x", "https://10.1/x"])
def test_lookalikes_and_other_networks_are_not_loopback(url):
    assert not _is_loopback_url(url)


class _FakeResponse:
    def __init__(self, status, headers, url):
        self.status, self.headers, self.url = status, headers, url

    def release(self):
        pass


class _ScriptedSession:
    def __init__(self, script):
        self.script, self.requested = script, []

    async def request(self, method, url, **kwargs):
        self.requested.append(url)
        return self.script[url]


@_pytest.mark.asyncio
@_pytest.mark.parametrize("loopback_target", ["http://127.0.0.1:9200/x", "https://127.1/x", "https://localhost./x"])
async def test_remote_origin_cannot_redirect_into_loopback(loopback_target):
    remote = "https://attacker.example/manual"
    session = _ScriptedSession({remote: _FakeResponse(302, {"Location": loopback_target}, remote)})
    with _pytest.raises(ValueError, match="never followed into loopback"):
        async with _safe_request_with_redirects(session, "GET", remote, context="manual discovery"):
            pass
    # The request to the agent's own service was never issued.
    assert session.requested == [remote]
