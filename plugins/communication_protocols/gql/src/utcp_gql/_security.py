"""URL validation for the GraphQL communication protocol.

Mirror of ``utcp_http._security`` -- intentionally duplicated rather
than cross-plugin-imported so ``utcp-gql`` does not gain a runtime
dependency on ``utcp-http``. Keep the two files in sync when changing
the validator behavior. Backs GHSA-ppx3-28rw-8fpf (the original CVE
fix did not reach this plugin) and GHSA-9qhg-99ww-9mqc (redirect
SSRF on the GraphQL endpoint).
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from ipaddress import IPv6Address, ip_address
from typing import Any, AsyncIterator, Dict, Optional
from urllib.parse import urljoin, urlparse

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


def _ip_is_loopback_like(host: str) -> bool:
    """Mirror of ``utcp_http._security._ip_is_loopback_like``. See that
    module for the full rationale -- covers 127.0.0.0/8, ::1, 0.0.0.0,
    ::, and IPv4-mapped IPv6 loopback addresses.
    """
    if host in {"0.0.0.0", "::"}:
        return True
    try:
        addr = ip_address(host)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    if isinstance(addr, IPv6Address):
        mapped = addr.ipv4_mapped
        if mapped is not None and mapped.is_loopback:
            return True
    return False


def is_loopback_url(url: str) -> bool:
    """Return True if ``url``'s host is a literal loopback-or-equivalent
    address. Hostname-based; covers ``0.0.0.0``, ``::`` and IPv4-mapped
    IPv6 loopback forms in addition to the obvious set.
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

    return _ip_is_loopback_like(host)


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


# HTTP statuses where the server expects the client to re-issue the request
# against the URL given in the ``Location`` header. 303 forces a GET; the
# rest preserve the original method.
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


_AUTH_SENSITIVE_HEADERS = frozenset({
    "authorization",
    "proxy-authorization",
    "cookie",
    "www-authenticate",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "x-access-token",
    "x-csrf-token",
    "x-xsrf-token",
    "x-amz-security-token",
    "x-goog-api-key",
})


_AUTH_HEADER_REGEX = re.compile(
    r"(^|-)(auth|authn|authz|token|key|secret|bearer|session|sid|api[_-]?key|jwt)(-|$)",
    re.IGNORECASE,
)


def _header_is_auth_sensitive(name: str) -> bool:
    if not isinstance(name, str):
        return False
    lower = name.lower()
    if lower in _AUTH_SENSITIVE_HEADERS:
        return True
    return _AUTH_HEADER_REGEX.search(lower) is not None


_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}


def _effective_port(scheme: str, parsed_port: Optional[int]) -> Optional[int]:
    if parsed_port is not None:
        return parsed_port
    return _DEFAULT_PORTS.get((scheme or "").lower())


def _same_origin(a: str, b: str) -> bool:
    """Return True iff URLs ``a`` and ``b`` share scheme+host+port.

    Treats omitted ports as the scheme default so default-port URLs
    are not falsely flagged as different origins.
    """
    try:
        pa, pb = urlparse(a), urlparse(b)
    except ValueError:
        return False
    sa = (pa.scheme or "").lower()
    sb = (pb.scheme or "").lower()
    if not sa or not sb:
        return False
    if sa != sb:
        return False
    if (pa.hostname or "").lower() != (pb.hostname or "").lower():
        return False
    return _effective_port(sa, pa.port) == _effective_port(sb, pb.port)


def _scrub_cross_origin_credentials(kwargs: dict) -> None:
    """Strip auth-bearing kwargs in place when crossing origins.

    Mirrors ``utcp_http._security._scrub_cross_origin_credentials`` --
    drops auth-looking headers, ``auth=`` / ``proxy_auth=``,
    ``cookies``, ``params``, and the request body (``json`` /
    ``data``) so 307/308 redirects cannot resend an OAuth POST body
    to a new origin.
    """
    headers = kwargs.get("headers")
    if headers is not None:
        scrubbed: Dict[str, Any] = {}
        for k, v in dict(headers).items():
            if _header_is_auth_sensitive(k):
                continue
            scrubbed[k] = v
        kwargs["headers"] = scrubbed

    kwargs.pop("auth", None)
    kwargs.pop("proxy_auth", None)
    kwargs.pop("cookies", None)
    kwargs.pop("params", None)
    kwargs.pop("json", None)
    kwargs.pop("data", None)


@asynccontextmanager
async def safe_request_with_redirects(
    session: Any,
    method: str,
    url: str,
    *,
    context: str,
    max_redirects: int = 5,
    **kwargs: Any,
) -> AsyncIterator[Any]:
    """Issue an aiohttp request that re-validates every redirect hop.

    Closes the residual SSRF window left by ``ensure_secure_url`` (which
    only inspects the initial URL): aiohttp by default follows 3xx
    redirects without rechecking, so an attacker-controlled server could
    302 the client into ``http://169.254.169.254/...`` (cloud metadata)
    or any internal HTTP service and the response body would be handed
    back to the caller. Backs GHSA-9qhg-99ww-9mqc.

    Behavior:
      * Calls ``ensure_secure_url(url, context=context)`` on the initial
        URL.
      * Disables aiohttp's auto-follow (``allow_redirects=False``).
      * On a 3xx response with a ``Location`` header, resolves the
        target against the current URL and runs ``ensure_secure_url``
        on it before issuing the next hop. Rejection raises and the
        redirect chain is aborted with the connection released.
      * Caps the chain at ``max_redirects`` hops. Exceeding that raises
        ``RuntimeError``.
      * Mirrors RFC 7231 method semantics: 303 forces ``GET`` and drops
        any request body; 301/302/307/308 preserve method and body.

    Usage:
        ```python
        async with safe_request_with_redirects(
            session, "GET", url, context="tool invocation", params=...
        ) as response:
            response.raise_for_status()
            ...
        ```
    """
    ensure_secure_url(url, context=context)
    # We control redirect behavior ourselves; refuse to let callers override.
    kwargs.pop("allow_redirects", None)

    current_url = url
    current_method = method
    hops = 0
    final_response = None

    try:
        while True:
            response = await session.request(
                current_method,
                current_url,
                allow_redirects=False,
                **kwargs,
            )
            if response.status not in _REDIRECT_STATUSES:
                final_response = response
                break

            location = response.headers.get("Location")
            if not location:
                # 3xx with no Location header — nothing to follow. Let
                # the caller handle the unusual response.
                final_response = response
                break

            if hops >= max_redirects:
                response.release()
                raise RuntimeError(
                    f"Too many redirects (>{max_redirects}) during {context} "
                    f"starting from {url!r}."
                )

            next_url = urljoin(current_url, location)
            try:
                ensure_secure_url(
                    next_url, context=f"{context} (redirect target)"
                )
            except Exception:
                response.release()
                raise

            response.release()

            # Strip auth-bearing kwargs on cross-origin redirect.
            if not _same_origin(current_url, next_url):
                _scrub_cross_origin_credentials(kwargs)

            if response.status == 303:
                current_method = "GET"
                kwargs.pop("json", None)
                kwargs.pop("data", None)
            current_url = next_url
            hops += 1

        yield final_response
    finally:
        if final_response is not None:
            final_response.release()
