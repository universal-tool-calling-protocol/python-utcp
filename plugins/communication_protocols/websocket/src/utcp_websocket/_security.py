"""URL validation for the WebSocket communication protocol.

Mirror of ``utcp_http._security`` -- intentionally duplicated rather
than cross-plugin-imported so ``utcp-websocket`` does not gain a
runtime dependency on ``utcp-http``. Keep in sync when changing the
validator behavior. Backs GHSA-ppx3-28rw-8fpf (the WebSocket plugin
was missing the URL check entirely, despite its docstrings claiming
"WSS or localhost only").

WebSocket URLs use the ``ws://`` and ``wss://`` schemes, so this
module exposes :func:`is_secure_ws_url` / :func:`ensure_secure_ws_url`
in addition to the HTTP-scheme helpers. ``wss://`` is always allowed;
``ws://`` is allowed only for literal loopback hosts.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from ipaddress import IPv6Address, ip_address
from typing import Any, AsyncIterator, Dict, Optional
from urllib.parse import urljoin, urlparse

# Hostnames considered safe to talk to over plain HTTP.
_LOOPBACK_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


def _ip_is_loopback_like(host: str) -> bool:
    """Mirror of ``utcp_http._security._ip_is_loopback_like``."""
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


def _hostname_is_loopback(host: str) -> bool:
    if host in _LOOPBACK_HOSTNAMES:
        return True
    return _ip_is_loopback_like(host)


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
    return _hostname_is_loopback(host)


def is_secure_ws_url(url: str) -> bool:
    """Return True if ``url`` is safe to open as a WebSocket connection.

    Allowed:
        - Any ``wss://`` URL.
        - ``ws://`` URLs whose host is a literal loopback address.

    Mirrors :func:`is_secure_url` for the WebSocket schemes. Backs the
    "WSS or localhost only" guarantee that the WebSocket plugin's
    docstrings advertise but the code did not previously enforce
    (GHSA-ppx3-28rw-8fpf).
    """
    if not isinstance(url, str) or not url:
        return False

    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    scheme = (parsed.scheme or "").lower()
    if scheme not in {"ws", "wss"}:
        return False

    host = (parsed.hostname or "").lower()
    if not host:
        return False

    if scheme == "wss":
        return True

    return _hostname_is_loopback(host)


def ensure_secure_ws_url(url: str, *, context: Optional[str] = None) -> None:
    """Raise ``ValueError`` if ``url`` is not safe to open as a WebSocket.

    Companion to :func:`ensure_secure_url` for WebSocket schemes.
    """
    if is_secure_ws_url(url):
        return

    where = f" during {context}" if context else ""
    raise ValueError(
        f"Security error{where}: WebSocket URL must use WSS or be a literal "
        f"loopback address (ws://localhost / ws://127.0.0.1 / ws://[::1]). "
        f"Got: {url!r}. Plain WS to any other host is rejected to prevent "
        "MITM attacks and SSRF into internal services."
    )


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
    "x_api_key",
    "api_key",
    "x_auth_token",
    "x_access_token",
    "x_csrf_token",
    "x_xsrf_token",
    "apikey",
    "xapikey",
    "authtoken",
    "xauthtoken",
    "accesstoken",
    "xaccesstoken",
    "bearertoken",
    "sessionid",
    "csrftoken",
    "xsrftoken",
})


_AUTH_HEADER_REGEX = re.compile(
    r"(?:(?:^|[-_])"
    r"(?:auth|authn|authz|token|key|secret|bearer|session|sid|"
    r"api[-_]?key|jwt|csrf|xsrf)"
    r"(?:[-_]|$))"
    r"|"
    r"(?:apikey|authtoken|accesstoken|bearertoken|sessionid|"
    r"csrftoken|xsrftoken|xapikey|xauthtoken|xaccesstoken|xapitoken)",
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

    Returns ``False`` on any parse failure, including
    ``urlparse(...).port`` raising for an out-of-range port -- a
    bogus ``Location`` is treated as cross-origin so credentials
    are scrubbed instead of letting the ``ValueError`` escape.
    """
    try:
        pa, pb = urlparse(a), urlparse(b)
        sa = (pa.scheme or "").lower()
        sb = (pb.scheme or "").lower()
        if not sa or not sb:
            return False
        if sa != sb:
            return False
        if (pa.hostname or "").lower() != (pb.hostname or "").lower():
            return False
        return _effective_port(sa, pa.port) == _effective_port(sb, pb.port)
    except ValueError:
        return False


def _scrub_cross_origin_credentials(
    kwargs: dict,
    extra_auth_header_names: Optional[frozenset] = None,
) -> None:
    """Strip auth-bearing kwargs in place when crossing origins.

    Mirrors ``utcp_http._security._scrub_cross_origin_credentials``.
    """
    extra = extra_auth_header_names or frozenset()
    headers = kwargs.get("headers")
    if headers is not None:
        scrubbed: Dict[str, Any] = {}
        for k, v in dict(headers).items():
            if _header_is_auth_sensitive(k):
                continue
            if isinstance(k, str) and k.lower() in extra:
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
    auth_header_names: Optional[Any] = None,
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

    extra_auth_header_names = frozenset(
        n.lower()
        for n in (auth_header_names or [])
        if isinstance(n, str)
    )

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
                _scrub_cross_origin_credentials(
                    kwargs, extra_auth_header_names
                )

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
