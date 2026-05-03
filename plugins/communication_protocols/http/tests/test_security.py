"""Tests for the URL trust-boundary helper used by every HTTP-based protocol.

The helper backs the fix for issue #83 (SSRF via attacker-controlled
``servers[0].url`` in OpenAPI specs). These cases pin the exact accept/reject
decisions so the bypass never silently regresses.
"""

import pytest

from utcp_http._security import ensure_secure_url, is_secure_url


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
