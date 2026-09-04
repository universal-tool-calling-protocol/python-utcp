"""Surface the server's error body on failed HTTP calls.

``aiohttp.ClientResponse.raise_for_status()`` raises a ``ClientResponseError``
whose ``message`` is only the reason phrase ("Forbidden"). Servers put the
real reason in the response body, typically ``{"error": "..."}``, and that
was discarded, so a refused call or discovery surfaced as nothing more than a
status code. Mirrors the TypeScript SDK's ``_normalizeToolError``.
"""
import json
from typing import Optional

import aiohttp

# Bodies are folded into an exception message; keep pathological ones bounded.
MAX_DETAIL_CHARS = 2000


def error_detail_from_body(text: str) -> Optional[str]:
    """Extract a human-readable reason from an error response body.

    Prefers a string ``error`` / ``message`` / ``detail`` field when the body is
    a JSON object; an object-valued field falls through to the raw JSON so the
    real structure shows. Returns ``None`` for an empty body.
    """
    body = text.strip()
    if not body:
        return None
    try:
        data = json.loads(body)
    except ValueError:
        return body[:MAX_DETAIL_CHARS]
    if isinstance(data, dict):
        for key in ("error", "message", "detail"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:MAX_DETAIL_CHARS]
    return body[:MAX_DETAIL_CHARS]


async def raise_for_status_with_body(response: aiohttp.ClientResponse) -> None:
    """Like ``response.raise_for_status()``, but with the response body in the error.

    On a 4xx/5xx, reads the body and raises a ``ClientResponseError`` of the
    same status and headers whose ``message`` is ``"<reason>: <detail>"``. The
    raw body text is attached as ``body`` for callers that want the structure.
    Does nothing on a 2xx/3xx.
    """
    if response.status < 400:
        return
    try:
        text = await response.text()
    except Exception:
        text = ""
    detail = error_detail_from_body(text)
    reason = response.reason or ""
    message = f"{reason}: {detail}" if detail else reason
    error = aiohttp.ClientResponseError(
        response.request_info,
        response.history,
        status=response.status,
        message=message,
        headers=response.headers,
    )
    error.body = text  # type: ignore[attr-defined]
    raise error
