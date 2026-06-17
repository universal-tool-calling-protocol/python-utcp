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
