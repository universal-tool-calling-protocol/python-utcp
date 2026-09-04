"""Surface the server's error body on failed HTTP calls.

``aiohttp.ClientResponse.raise_for_status()`` raises a ``ClientResponseError``
whose ``message`` is only the reason phrase ("Forbidden"). Servers put the
real reason in the response body, typically ``{"error": "..."}``, and that
was discarded, so a refused call or discovery surfaced as nothing more than a
status code. Mirrors the TypeScript SDK's ``_normalizeToolError``.
"""
import json
import re
from typing import Optional

import aiohttp

# Bodies are folded into an exception message; keep pathological ones bounded.
MAX_DETAIL_CHARS = 2000

# How much of an error body is read at all. The response may come from an
# attacker-controlled endpoint (discovery URLs are exactly that trust
# surface), so the read is bounded up front rather than buffered in full and
# truncated afterwards. Comfortably larger than MAX_DETAIL_CHARS so a JSON
# body with a long ``error`` field still parses.
MAX_BODY_READ_BYTES = 64 * 1024

_DETAIL_KEYS = ("error", "message", "detail")

# Control characters (newlines, ANSI escape introducers, NUL) are collapsed so
# server-controlled text folded into an exception message or a log line cannot
# forge extra log records or terminal escape sequences.
# C0 and C1 control ranges: C1 (U+0080..U+009F) carries escape introducers too.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]+")


def _clean(text: str) -> str:
    return _CONTROL_CHARS.sub(" ", text).strip()[:MAX_DETAIL_CHARS]


def error_detail_from_body(text: str) -> Optional[str]:
    """Extract a human-readable reason from an error response body.

    When the body is a JSON object, the first of ``error`` / ``message`` /
    ``detail`` that is present decides: a non-empty string is returned as the
    reason; anything else (an object, a list, a number) means the server sent a
    structured error, so the raw JSON is returned to keep that structure
    visible rather than skipping ahead to a lower-priority generic string.
    A non-JSON body is returned as-is. Returns ``None`` for an empty body.
    """
    body = text.strip()
    if not body:
        return None
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        # RecursionError: a deeply nested body ("[[[[...") within the read cap
        # can exceed the parser's recursion limit; it is still just text.
        return _clean(body)
    if isinstance(data, dict):
        for key in _DETAIL_KEYS:
            if key not in data or data[key] is None:
                continue
            value = data[key]
            if isinstance(value, str):
                if value.strip():
                    return _clean(value)
                continue
            # Structured error: show it rather than a later generic string.
            return _clean(body)
    return _clean(body)


async def _read_body_bounded(response: aiohttp.ClientResponse, limit: int) -> str:
    """Read at most ``limit`` bytes of the body and decode them leniently."""
    chunks = []
    total = 0
    async for chunk in response.content.iter_chunked(8192):
        chunks.append(chunk)
        total += len(chunk)
        if total >= limit:
            break
    raw = b"".join(chunks)[:limit]
    # ``charset`` only parses the Content-Type header, but stay defensive: the
    # body was read directly, so aiohttp's own buffered-body machinery must not
    # be relied on, and an unknown charset name must not lose the detail.
    try:
        return raw.decode(response.charset or "utf-8", errors="replace")
    except (LookupError, RuntimeError, ValueError):
        return raw.decode("utf-8", errors="replace")


async def raise_for_status_with_body(response: aiohttp.ClientResponse) -> None:
    """Like ``response.raise_for_status()``, but with the response body in the error.

    On a 4xx/5xx, reads up to ``MAX_BODY_READ_BYTES`` of the body and raises a
    ``ClientResponseError`` of the same status and headers whose ``message`` is
    ``"<reason>: <detail>"``. The text that was read is attached as ``body``
    for callers that want the structure. Does nothing on a 2xx/3xx.
    """
    if response.status < 400:
        return
    try:
        text = await _read_body_bounded(response, MAX_BODY_READ_BYTES)
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
