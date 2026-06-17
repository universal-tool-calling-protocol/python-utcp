"""Tests for the URL trust-boundary helper used by every HTTP-based protocol.

The helper backs the fix for issue #83 (SSRF via attacker-controlled
``servers[0].url`` in OpenAPI specs). These cases pin the exact accept/reject
decisions so the bypass never silently regresses.
"""

import pytest

from utcp_http._security import (
    ensure_secure_url,
    is_loopback_url,
    is_secure_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/openapi.json",
        "HTTPS://example.com/openapi.json",
        "https://example.com:8443/v1/tool",
        "http://localhost/openapi.json",
        "http://localhost:8080/v1/tool",
        "http://127.0.0.1:9090/sensitive",
        "http://[::1]:9090/sensitive",
    ],
)
def test_secure_urls_accepted(url: str) -> None:
    assert is_secure_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        # Plain http to non-loopback host (the historical SSRF target).
        "http://169.254.169.254/latest/meta-data/",
        "http://internal.service.local/secret",
        "http://10.0.0.5/admin",
        "http://example.com/openapi.json",
        # The localhost.evil.com / 127.0.0.1.attacker.example bypass that the
        # original `startswith` check let through.
        "http://localhost.evil.com/path",
        "http://127.0.0.1.attacker.example/path",
        # Non-http schemes must always be rejected.
        "file:///etc/passwd",
        "ftp://example.com/x",
        "javascript:alert(1)",
        # Garbage.
        "",
        "not-a-url",
    ],
)
def test_insecure_urls_rejected(url: str) -> None:
    assert is_secure_url(url) is False


def test_ensure_secure_url_raises_with_context() -> None:
    with pytest.raises(ValueError) as exc:
        ensure_secure_url(
            "http://169.254.169.254/latest/meta-data/",
            context="tool invocation",
        )
    msg = str(exc.value)
    assert "tool invocation" in msg
    assert "169.254.169.254" in msg


def test_ensure_secure_url_passes_silently_for_valid_url() -> None:
    # Should not raise.
    ensure_secure_url("https://example.com/v1/tool", context="manual discovery")


# --- is_loopback_url --------------------------------------------------------

from utcp_http._security import is_loopback_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/x",
        "http://localhost:9090/x",
        "http://127.0.0.1/x",
        "http://127.0.0.1:8080/x",
        "http://[::1]:9090/x",
        "https://localhost/x",
    ],
)
def test_loopback_urls_detected(url: str) -> None:
    assert is_loopback_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/x",
        "http://10.0.0.5/x",
        "http://example.com/x",
        # The historical hostname-prefix bypass must NOT register as loopback.
        "http://localhost.evil.com/x",
        "http://127.0.0.1.attacker.example/x",
        "",
        "not-a-url",
    ],
)
def test_non_loopback_urls_rejected(url: str) -> None:
    assert is_loopback_url(url) is False


# --- OpenAPI converter SSRF defense -----------------------------------------

from utcp_http.openapi_converter import OpenApiConverter


def _spec_with_server(server_url: str) -> dict:
    return {
        "openapi": "3.0.0",
        "info": {"title": "T"},
        "servers": [{"url": server_url}],
        "paths": {
            "/x": {"get": {"operationId": "x", "responses": {"200": {"description": "ok"}}}}
        },
    }


def test_converter_rejects_loopback_server_from_remote_spec() -> None:
    """A remote (non-loopback) OpenAPI spec must not redirect at loopback."""
    converter = OpenApiConverter(
        _spec_with_server("http://127.0.0.1:9090"),
        spec_url="https://attacker.example/openapi.json",
    )
    with pytest.raises(ValueError) as exc:
        converter.convert()
    assert "loopback" in str(exc.value).lower()
    assert "GHSA-39j6-4867-gg4w" in str(exc.value)


def test_converter_allows_loopback_server_from_loopback_spec() -> None:
    """Local-dev case: spec from localhost can declare a localhost server."""
    converter = OpenApiConverter(
        _spec_with_server("http://127.0.0.1:9090"),
        spec_url="http://localhost:8000/openapi.json",
    )
    manual = converter.convert()
    assert len(manual.tools) == 1


def test_converter_allows_explicit_base_url_override() -> None:
    """If the user explicitly overrides base_url, we trust the user."""
    converter = OpenApiConverter(
        _spec_with_server("http://127.0.0.1:9090"),
        spec_url="https://attacker.example/openapi.json",
        base_url="http://127.0.0.1:9090",
    )
    manual = converter.convert()
    assert len(manual.tools) == 1


def test_converter_allows_remote_server_from_remote_spec() -> None:
    """Normal case: remote spec, remote server."""
    converter = OpenApiConverter(
        _spec_with_server("https://api.example.com"),
        spec_url="https://api.example.com/openapi.json",
    )
    manual = converter.convert()
    assert len(manual.tools) == 1


# ---------------------------------------------------------------------------
# Extended loopback detection -- post-audit hardening for the OpenAPI
# converter's loopback check. The narrow set (``localhost`` / 127.0.0.1
# / ::1) missed wildcard binds (``0.0.0.0`` / ``::``), the rest of the
# 127.0.0.0/8 range, and IPv4-mapped IPv6 loopback forms, all of which
# the kernel routes to local services.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://0.0.0.0/",
        "http://[::]/",
        "http://127.0.0.2/",
        "http://127.255.255.254/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:7f00:1]/",
        "https://0.0.0.0/",
        "https://[::ffff:127.0.0.5]/",
    ],
)
def test_is_loopback_url_catches_wildcard_and_v4_mapped(url: str) -> None:
    assert is_loopback_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://203.0.113.5/",
        "http://[2001:db8::1]/",
        "http://[::ffff:8.8.8.8]/",
    ],
)
def test_is_loopback_url_rejects_non_loopback(url: str) -> None:
    assert is_loopback_url(url) is False


def test_converter_rejects_wildcard_server_from_remote_spec() -> None:
    """``0.0.0.0`` on Linux is reachable as localhost -- treat it like
    a loopback declaration for SSRF defense purposes."""
    converter = OpenApiConverter(
        _spec_with_server("http://0.0.0.0:9090"),
        spec_url="https://attacker.example/openapi.json",
    )
    with pytest.raises(ValueError) as exc:
        converter.convert()
    assert "loopback" in str(exc.value).lower()


def test_converter_rejects_v4_mapped_loopback_from_remote_spec() -> None:
    converter = OpenApiConverter(
        _spec_with_server("http://[::ffff:127.0.0.1]:9090"),
        spec_url="https://attacker.example/openapi.json",
    )
    with pytest.raises(ValueError) as exc:
        converter.convert()
    assert "loopback" in str(exc.value).lower()


def test_converter_rejects_127_x_x_x_from_remote_spec() -> None:
    converter = OpenApiConverter(
        _spec_with_server("http://127.0.0.2:9090"),
        spec_url="https://attacker.example/openapi.json",
    )
    with pytest.raises(ValueError) as exc:
        converter.convert()
    assert "loopback" in str(exc.value).lower()
