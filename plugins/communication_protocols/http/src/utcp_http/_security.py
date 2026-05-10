"""URL validation shared by every HTTP-based communication protocol.

Centralised so all three HTTP protocols (http, streamable_http, sse) enforce
the same trust boundary at every network edge — manual discovery AND tool
invocation. Issue #83 (CVE-class SSRF) was caused by the runtime invocation
path forgetting the discovery-time check, so this module also provides an
explicit ``ensure_secure_url`` to call before every aiohttp request.
"""

from __future__ import annotations

from ipaddress import ip_address
from typing import Optional
from urllib.parse import urlparse

# Hostnames considered safe to talk to over plain HTTP.
_LOOPBACK_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


def is_secure_url(url: str) -> bool:
    """Return True if ``url`` is safe to fetch from a UTCP HTTP protocol.

    Allowed:
        - Any ``https://`` URL.
        - ``http://`` URLs whose host is exactly ``localhost``, ``127.0.0.1``,
          or ``::1``.

    Disallowed:
        - Plain ``http://`` to any other host (MITM exposure).
        - URLs whose hostname *starts* with ``localhost`` / ``127.0.0.1`` but
          isn't actually loopback (e.g. ``http://localhost.evil.com``,
          ``http://127.0.0.1.attacker.example``). The earlier ``startswith``
          check let these through.
        - Anything without a scheme/host (file://, gopher://, javascript:, ...).
    """
    if not isinstance(url, str) or not url:
        return False

    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return False

    host = (parsed.hostname or "").lower()
    if not host:
        return False

    if scheme == "https":
        return True

    # http:// is only allowed for loopback.
    if host in _LOOPBACK_HOSTNAMES:
        return True

    # Catch any other literal loopback IP that urlparse normalised
    # (e.g. ``http://127.000.000.001``).
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def is_loopback_url(url: str) -> bool:
    """Return True if ``url``'s host is a literal loopback address.

    Used by the OpenAPI converter to detect the SSRF case where a remote spec
    declares ``servers: [{ url: "http://127.0.0.1:..." }]`` to redirect tool
    invocation at the host running the agent. Hostname-based — not a string
    prefix — so ``http://localhost.evil.com`` returns False.
    """
    if not isinstance(url, str) or not url:
        return False

    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    host = (parsed.hostname or "").lower()
    if not host:
        return False

    if host in _LOOPBACK_HOSTNAMES:
        return True

    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def ensure_secure_url(url: str, *, context: Optional[str] = None) -> None:
    """Raise ``ValueError`` if ``url`` is not safe to fetch.

    ``context`` is a short label (``"manual discovery"``, ``"tool invocation"``,
    etc.) included in the error so log readers can tell which trust boundary
    was breached.
    """
    if is_secure_url(url):
        return

    where = f" during {context}" if context else ""
    raise ValueError(
        f"Security error{where}: URL must use HTTPS or be a literal loopback "
        f"address (localhost / 127.0.0.1 / ::1). Got: {url!r}. "
        "Plain HTTP to any other host is rejected to prevent MITM attacks "
        "and SSRF into internal services."
    )
