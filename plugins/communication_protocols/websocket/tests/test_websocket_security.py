"""Security tests for the WebSocket communication protocol
(utcp-websocket).

Pin the fixes for GHSA-ppx3-28rw-8fpf: the previous implementation
did NO URL validation at all despite its docstrings advertising
"WSS or localhost only", letting any ``ws://`` URL connect (with
credentials attached) to an attacker-controlled host. Also covers
the OAuth2 / redirect halves of GHSA-8cp3-qxj6-px34 and
GHSA-9qhg-99ww-9mqc.
"""

import json

import pytest

from utcp.data.auth_implementations.oauth2_auth import OAuth2Auth
from utcp_websocket._security import (
    ensure_secure_url,
    ensure_secure_ws_url,
    is_secure_url,
    is_secure_ws_url,
)
from utcp_websocket.websocket_call_template import WebSocketCallTemplate
from utcp_websocket.websocket_communication_protocol import (
    WebSocketCommunicationProtocol,
)


# ---------------------------------------------------------------------------
# WebSocket-scheme validator: ws:// is loopback-only, wss:// always OK.
# ---------------------------------------------------------------------------


class TestWebSocketUrlValidator:
    @pytest.mark.parametrize(
        "url",
        [
            "wss://api.example.com/socket",
            "ws://localhost/socket",
            "ws://127.0.0.1:9090/socket",
            "ws://[::1]:9090/socket",
        ],
    )
    def test_secure_ws_url_accepted(self, url: str) -> None:
        assert is_secure_ws_url(url) is True
        ensure_secure_ws_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            # Plain ws:// to non-loopback host (MITM + SSRF surface).
            "ws://169.254.169.254/socket",
            "ws://internal.service.local/socket",
            "ws://10.0.0.5/socket",
            "ws://example.com/socket",
            # The localhost.evil.com / 127.0.0.1.attacker.example bypass:
            # not loopback even though the prefix looks like it.
            "ws://localhost.evil.com/socket",
            "ws://127.0.0.1.attacker.example/socket",
            # HTTP schemes are not WebSocket URLs.
            "http://localhost/socket",
            "https://api.example.com/socket",
            # Junk inputs.
            "",
            "not-a-url",
            "javascript:alert(1)",
        ],
    )
    def test_insecure_ws_url_rejected(self, url: str) -> None:
        assert is_secure_ws_url(url) is False
        with pytest.raises(ValueError, match="WebSocket URL"):
            ensure_secure_ws_url(url)


# ---------------------------------------------------------------------------
# _get_connection enforces ensure_secure_ws_url -- the plugin used to
# accept any URL silently.
# ---------------------------------------------------------------------------


class TestTemplateRejectsBypass:
    """The Pydantic field validator on WebSocketCallTemplate is the
    first line of defence -- with the new hostname-based check it
    catches the prefix bypass that the original ``startswith`` form
    let through.
    """

    @pytest.mark.parametrize(
        "url",
        [
            "ws://169.254.169.254/",
            "ws://localhost.evil.com/socket",
            "ws://127.0.0.1.attacker.example/socket",
            "ws://example.com/socket",
            "http://localhost/socket",  # not a WebSocket scheme
        ],
    )
    def test_template_rejects_bypass(self, url: str) -> None:
        with pytest.raises(Exception) as exc_info:
            WebSocketCallTemplate(name="ws", url=url)
        # Pydantic wraps the message inside its own ValidationError --
        # the underlying ValueError text must still be present so
        # operators can see what was rejected.
        assert "WebSocket URL" in str(exc_info.value)


class TestGetConnectionRejectsLoopbackBypass:
    """Defence in depth: ``_get_connection`` itself runs the same
    hostname-based check so a template that bypassed the Pydantic
    validator (e.g. constructed without ``model_validate``) still
    cannot open the WebSocket.
    """

    @pytest.mark.asyncio
    async def test_connection_rejected_when_template_bypassed(self) -> None:
        proto = WebSocketCommunicationProtocol()
        # Construct a template that *would* fail the field validator,
        # but skip validation by going through ``model_construct``.
        tpl = WebSocketCallTemplate.model_construct(
            name="ws",
            url="ws://localhost.evil.com/socket",
            call_template_type="websocket",
            keep_alive=True,
            timeout=30,
        )
        with pytest.raises(ValueError, match="WebSocket URL"):
            await proto._get_connection(tpl)


# ---------------------------------------------------------------------------
# OAuth2 token URL is validated (the WebSocket plugin's OAuth2 path
# goes over HTTP, so it uses ensure_secure_url not ensure_secure_ws_url).
# ---------------------------------------------------------------------------


class TestOAuth2TokenUrlValidation:
    @pytest.mark.asyncio
    async def test_internal_token_url_rejected(self) -> None:
        proto = WebSocketCommunicationProtocol()
        auth = OAuth2Auth(
            token_url="http://169.254.169.254/token",
            client_id="victim-id",
            client_secret="victim-secret",
        )
        with pytest.raises(ValueError, match="OAuth2 token URL"):
            await proto._handle_oauth2(auth)

    @pytest.mark.asyncio
    async def test_plain_http_non_loopback_token_url_rejected(self) -> None:
        proto = WebSocketCommunicationProtocol()
        auth = OAuth2Auth(
            token_url="http://attacker.example/token",
            client_id="victim-id",
            client_secret="victim-secret",
        )
        with pytest.raises(ValueError, match="OAuth2 token URL"):
            await proto._handle_oauth2(auth)


# ---------------------------------------------------------------------------
# Sanity: the HTTP-scheme validator is also re-exported (the OAuth2
# token endpoint goes over HTTP/HTTPS).
# ---------------------------------------------------------------------------


class TestJsonInjectionInMessageTemplate:
    """The ``message`` field of ``WebSocketCallTemplate`` accepts both a
    dict (recommended) and a raw string (legacy / fully-flexible). A
    string template that the caller WROTE as JSON used to pass
    user-supplied ``"`` chars through unescaped, letting tool args
    inject extra fields. Dict templates were already safe because
    ``json.dumps`` runs at the end.
    """

    def test_json_string_template_escapes_tool_arg(self):
        proto = WebSocketCommunicationProtocol()
        # Template is a JSON-shaped STRING -- our heuristic should kick
        # in and json-escape every string substitution.
        tpl = WebSocketCallTemplate.model_construct(
            name="ws",
            url="wss://example.com/socket",
            call_template_type="websocket",
            keep_alive=True,
            timeout=30,
            message='{"q": "UTCP_ARG_q_UTCP_ARG"}',
        )
        msg = proto._format_tool_call_message(
            "x",
            {"q": '", "isAdmin": true, "x": "'},
            tpl,
            "req-1",
        )
        # Parsed payload should have exactly one field whose value is
        # the literal attacker payload -- no smuggled isAdmin.
        parsed = json.loads(msg)
        assert set(parsed.keys()) == {"q"}
        assert parsed["q"] == '", "isAdmin": true, "x": "'

    def test_dict_template_escapes_tool_arg(self):
        """Dict template path: already safe; pin the behaviour."""
        proto = WebSocketCommunicationProtocol()
        tpl = WebSocketCallTemplate.model_construct(
            name="ws",
            url="wss://example.com/socket",
            call_template_type="websocket",
            keep_alive=True,
            timeout=30,
            message={"q": "UTCP_ARG_q_UTCP_ARG"},
        )
        msg = proto._format_tool_call_message(
            "x",
            {"q": '", "isAdmin": true, "x": "'},
            tpl,
            "req-1",
        )
        parsed = json.loads(msg)
        assert set(parsed.keys()) == {"q"}
        assert parsed["q"] == '", "isAdmin": true, "x": "'

    def test_non_json_string_template_substitutes_raw(self):
        """Non-JSON-shaped string template should NOT escape (back-
        compat -- e.g. a template like ``GET /x?q=UTCP_ARG_q_UTCP_ARG``).
        """
        proto = WebSocketCommunicationProtocol()
        tpl = WebSocketCallTemplate.model_construct(
            name="ws",
            url="wss://example.com/socket",
            call_template_type="websocket",
            keep_alive=True,
            timeout=30,
            message="GET /x?q=UTCP_ARG_q_UTCP_ARG",
        )
        msg = proto._format_tool_call_message(
            "x",
            {"q": "value"},
            tpl,
            "req-1",
        )
        assert msg == "GET /x?q=value"


class TestHttpUrlValidator:
    def test_https_accepted(self) -> None:
        assert is_secure_url("https://api.example.com/oauth/token") is True
        ensure_secure_url("https://api.example.com/oauth/token")

    def test_internal_rejected(self) -> None:
        assert is_secure_url("http://169.254.169.254/token") is False
        with pytest.raises(ValueError):
            ensure_secure_url("http://169.254.169.254/token")
