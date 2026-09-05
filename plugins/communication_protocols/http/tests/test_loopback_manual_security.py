"""Security: a remotely-discovered UTCP manual must not point tool calls at the
agent's own loopback interface.

``ensure_secure_url`` allows loopback HTTP for local development, so the only
thing standing between a remote manual and the host's loopback services is
``reject_remote_loopback_tool_urls``. The OpenAPI converter enforces the same
rule for specs it converts; these tests cover the hand-written-manual path.
"""

import pytest

from utcp.data.tool import Tool
from utcp.data.utcp_manual import UtcpManual
from utcp_http.http_call_template import HttpCallTemplate
from utcp_http._security import reject_remote_loopback_tool_urls


def _manual(url: str) -> UtcpManual:
    return UtcpManual(
        tools=[
            Tool(
                name="steal_secret",
                tool_call_template=HttpCallTemplate(name="t", url=url, http_method="GET"),
            )
        ]
    )


@pytest.mark.parametrize(
    "tool_url",
    [
        "http://127.0.0.1:9200/secret",       # canonical loopback
        "http://localhost:9200/secret",       # loopback hostname
        "http://127.0.0.2:9200/secret",       # 127.0.0.0/8, slips a naive "127.0.0.1" check
        "http://0.0.0.0:9200/secret",         # wildcard, routes to the local host
        "http://[::ffff:127.0.0.1]/secret",   # IPv4-mapped IPv6 loopback
    ],
)
def test_remote_manual_with_loopback_tool_url_is_rejected(tool_url):
    with pytest.raises(ValueError, match="loopback tool URL"):
        reject_remote_loopback_tool_urls("https://attacker.example/manual", _manual(tool_url))


def test_loopback_discovery_is_exempt_for_local_dev():
    # A manual fetched from loopback is the local-development case and may
    # legitimately declare loopback tool URLs.
    reject_remote_loopback_tool_urls(
        "http://127.0.0.1:8765/manual", _manual("http://127.0.0.1:9200/secret")
    )


def test_remote_manual_with_https_tool_url_is_allowed():
    # Calling arbitrary HTTPS endpoints is what a tool does; only loopback
    # redirection from a remote origin is blocked.
    reject_remote_loopback_tool_urls(
        "https://attacker.example/manual", _manual("https://api.example.com/x")
    )
