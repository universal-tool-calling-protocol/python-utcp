"""URL validation shared by every HTTP-based communication protocol.

Centralised so all three HTTP protocols (http, streamable_http, sse) enforce
the same trust boundary at every network edge — manual discovery AND tool
invocation. Issue #83 (CVE-class SSRF) was caused by the runtime invocation
path forgetting the discovery-time check, so this module also provides an
explicit ``ensure_secure_url`` to call before every aiohttp request.
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
    """Return True if ``host`` is an IP literal that the local kernel will
    route to the host running the agent.

    Wider than Python's stdlib ``ip_address(...).is_loopback`` because we
    must also defend against:

    * ``0.0.0.0`` -- on Linux a TCP connect to 0.0.0.0 lands on 127.0.0.1.
    * ``::`` -- the IPv6 equivalent of ``0.0.0.0``.
    * IPv4-mapped IPv6 forms of any 127.0.0.0/8 address (e.g.
      ``::ffff:127.0.0.1``, ``::ffff:127.0.0.2``) -- ``ipaddress`` does
      not treat these as loopback per RFC 4291, but the dual-stack
      socket layer routes them to the v4 loopback.

    Used by the OpenAPI converter to detect attacker-controlled
    ``servers[0].url`` values that point at the agent's own loopback
    interface (the GHSA-39j6-4867-gg4w SSRF pattern). Hostname-based,
    never prefix-based.
    """
    if host in {"0.0.0.0", "::"}:
        return True
    try:
        addr = ip_address(host)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    # IPv4-mapped IPv6 loopback (``::ffff:127.0.0.1`` etc.) -- the
    # ``ipv4_mapped`` accessor surfaces the embedded v4 address.
    if isinstance(addr, IPv6Address):
        mapped = addr.ipv4_mapped
        if mapped is not None and mapped.is_loopback:
            return True
    return False


def is_loopback_url(url: str) -> bool:
    """Return True if ``url``'s host is a literal loopback address.

    Used by the OpenAPI converter to detect the SSRF case where a remote spec
    declares ``servers: [{ url: "http://127.0.0.1:..." }]`` to redirect tool
    invocation at the host running the agent. Hostname-based — not a string
    prefix — so ``http://localhost.evil.com`` returns False. Also covers the
    "wildcard" and "IPv4-mapped" loopback forms that bypass Python's stdlib
    ``is_loopback`` check (see ``_ip_is_loopback_like``).
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


# HTTP headers that carry authentication or session material and must be
# stripped when a redirect crosses to a different origin. Includes the
# canonical IETF names (``Authorization`` / ``Cookie`` /
# ``Proxy-Authorization``) PLUS a curated list of common API-key /
# service-token names because UTCP's ``ApiKeyAuth`` lets callers put a
# secret under an arbitrary header name. Comparison is case-insensitive
# against this lowercase set.
_AUTH_SENSITIVE_HEADERS = frozenset({
    "authorization",
    "proxy-authorization",
    "cookie",
    "www-authenticate",
    # Common API-key / service-token header names.
    "x-api-key",
    "api-key",
    "x-auth-token",
    "x-access-token",
    "x-csrf-token",
    "x-xsrf-token",
    "x-amz-security-token",
    "x-goog-api-key",
})

# Regex catching ad-hoc auth header names that aren't in the explicit
# set above (``X-MyApp-Token``, ``Custom-Bearer``, etc.). Conservative
# but biased toward strip-on-cross-origin since false positives are
# only a usability cost.
_AUTH_HEADER_REGEX = re.compile(
    r"(^|-)(auth|authn|authz|token|key|secret|bearer|session|sid|api[_-]?key|jwt)(-|$)",
    re.IGNORECASE,
)


def _header_is_auth_sensitive(name: str) -> bool:
    """Return True if ``name`` looks like it carries an auth secret."""
    if not isinstance(name, str):
        return False
    lower = name.lower()
    if lower in _AUTH_SENSITIVE_HEADERS:
        return True
    return _AUTH_HEADER_REGEX.search(lower) is not None


_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}


def _effective_port(scheme: str, parsed_port: Optional[int]) -> Optional[int]:
    """Return the port a URL actually targets, filling in scheme defaults."""
    if parsed_port is not None:
        return parsed_port
    return _DEFAULT_PORTS.get((scheme or "").lower())


def _same_origin(a: str, b: str) -> bool:
    """Return True iff URLs ``a`` and ``b`` share scheme+host+port.

    Treats omitted ports as the scheme default, so
    ``https://api.example.com/`` and ``https://api.example.com:443/``
    are recognised as the same origin (the previous implementation
    treated them as different origins and silently stripped
    ``Authorization`` on legitimate same-origin redirects).
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

    Aligns the redirect helper with browser / requests / curl
    behaviour: do not forward credential-bearing material to a new
    origin. Covers:

    * ``Authorization`` and other canonical auth headers
      (``Proxy-Authorization``, ``Cookie``, ``WWW-Authenticate``);
    * common API-key / service-token header names
      (``X-Api-Key``, ``X-Auth-Token``, ``X-Csrf-Token``,
      ``X-Amz-Security-Token``, etc.);
    * ad-hoc header names matching auth-like substrings (e.g.
      ``X-MyApp-Bearer``, ``Custom-Token``) -- see
      ``_AUTH_HEADER_REGEX``;
    * the aiohttp ``auth=`` Basic-credentials kwarg;
    * the ``proxy_auth=`` Basic-credentials kwarg;
    * ``cookies``;
    * ``params`` (API keys configured via ``ApiKeyAuth`` with
      ``location="query"`` end up here);
    * the request body (``json``, ``data``) -- a 307/308 redirect
      preserves method+body, and the body of e.g. an OAuth2 token
      POST contains the very credentials we're trying to protect.
      Browsers prompt the user before forwarding a cross-origin
      307/308 body; we are headless and have no user, so refuse
      instead.

    Callers invoke this BEFORE issuing the next hop, only when the
    redirect target's origin differs from the current URL's origin.
    """
    headers = kwargs.get("headers")
    if headers is not None:
        # Build a new dict so we never mutate the caller's headers
        # object across iterations / shared references.
        scrubbed: Dict[str, Any] = {}
        for k, v in dict(headers).items():
            if _header_is_auth_sensitive(k):
                continue
            scrubbed[k] = v
        kwargs["headers"] = scrubbed

    # aiohttp's per-request basic-auth credentials.
    kwargs.pop("auth", None)
    # aiohttp's per-request proxy basic-auth credentials.
    kwargs.pop("proxy_auth", None)
    # Cookie jar / dict.
    kwargs.pop("cookies", None)
    # Query-string params commonly carry API keys (``ApiKeyAuth`` with
    # ``location="query"``). Drop the whole dict on cross-origin --
    # the cost of a broken non-auth query param is small compared to
    # the risk of leaking a token.
    kwargs.pop("params", None)
    # Request body. 307/308 would otherwise preserve and resend it to
    # the new origin -- the OAuth token-POST case is the headline
    # exploit.
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

            # Strip auth-bearing kwargs when the redirect crosses to a
            # different origin. Without this an attacker-controlled
            # endpoint could 302 us to their own server and our
            # Authorization header / Basic auth / cookies / query
            # API key would be forwarded along. Mirrors browser /
            # requests / curl behaviour.
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
