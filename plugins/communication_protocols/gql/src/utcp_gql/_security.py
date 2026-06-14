"""URL validation for the GraphQL communication protocol.

Mirror of ``utcp_http._security`` -- intentionally duplicated rather
than cross-plugin-imported so ``utcp-gql`` does not gain a runtime
dependency on ``utcp-http``. Keep the two files in sync when changing
the validator behavior. Backs GHSA-ppx3-28rw-8fpf (the original CVE
fix did not reach this plugin) and GHSA-9qhg-99ww-9mqc (redirect
SSRF on the GraphQL endpoint).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from ipaddress import ip_address
from typing import Any, AsyncIterator, Optional
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


# HTTP statuses where the server expects the client to re-issue the request
# against the URL given in the ``Location`` header. 303 forces a GET; the
# rest preserve the original method.
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


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
