import sys
from typing import Dict, Any, List, Optional, Callable, AsyncIterator, AsyncGenerator
import aiohttp
import json
import asyncio
import codecs
import re
from urllib.parse import quote
import base64

from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool
from utcp.data.utcp_manual import UtcpManual, UtcpManualSerializer
from utcp.data.register_manual_response import RegisterManualResult
from utcp.data.auth_implementations.api_key_auth import ApiKeyAuth
from utcp.data.auth_implementations.basic_auth import BasicAuth
from utcp.data.auth_implementations.oauth2_auth import OAuth2Auth
from utcp_http.sse_call_template import SseCallTemplate
from aiohttp import ClientSession, BasicAuth as AiohttpBasicAuth
from utcp_http._errors import raise_for_status_with_body
from utcp_http._security import ensure_secure_url, safe_request_with_redirects, reject_remote_loopback_tool_urls
import traceback
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
)

logger = logging.getLogger(__name__)


class SseProtocolError(RuntimeError):
    """The server violated the SSE wire format. Not a connection loss, so never retried."""


class SseCommunicationProtocol(CommunicationProtocol):
    """REQUIRED
    SSE communication protocol implementation for UTCP client.
    
    Handles Server-Sent Events based tool providers with streaming capabilities.
    """

    # Upper bound on reconnection attempts for a single tool call when the
    # established stream drops and the call template has ``reconnect`` enabled.
    # Keeps a tool call bounded even if the server keeps dropping the connection.
    MAX_RECONNECT_ATTEMPTS: int = 5
    # Cap on the delay before a reconnect, whatever ``retry_timeout`` or a
    # server-sent ``retry:`` field asks for. Together with MAX_RECONNECT_ATTEMPTS
    # this bounds the total time a call can spend waiting to reconnect.
    MAX_RECONNECT_DELAY_MS: int = 60_000
    # Time allowed for the SSE handshake, i.e. until response headers arrive.
    # Reading the body is unbounded: an SSE stream may legitimately stay quiet.
    HANDSHAKE_TIMEOUT_SECONDS: float = 30.0
    # Largest partial event the parser buffers before declaring the stream
    # malformed. Guards against a server that streams data without ever sending
    # the blank-line event delimiter.
    MAX_EVENT_BUFFER_CHARS: int = 16 * 1024 * 1024

    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _assert_no_crlf(value: Optional[str], field_name: str) -> None:
        if not isinstance(value, str):
            return
        if "\r" in value or "\n" in value:
            raise ValueError(
                f"Refusing to construct request: {field_name} contains CR/LF, "
                f"which would enable HTTP header injection."
            )

    def _apply_auth(self, provider: SseCallTemplate, headers: Dict[str, str], query_params: Dict[str, Any]) -> tuple:
        """Apply authentication to the request based on the provider's auth configuration.

        Returns:
            tuple ``(auth_obj, cookies, auth_header_names)``.
        """
        auth = None
        cookies = {}
        auth_header_names: List[str] = []

        if provider.auth:
            if isinstance(provider.auth, ApiKeyAuth):
                if provider.auth.api_key:
                    self._assert_no_crlf(provider.auth.var_name, "ApiKeyAuth.var_name")
                    if provider.auth.location == "header":
                        headers[provider.auth.var_name] = provider.auth.api_key
                        auth_header_names.append(provider.auth.var_name)
                    elif provider.auth.location == "query":
                        query_params[provider.auth.var_name] = provider.auth.api_key
                    elif provider.auth.location == "cookie":
                        cookies[provider.auth.var_name] = provider.auth.api_key
                else:
                    logger.error("API key not found for ApiKeyAuth.")
                    raise ValueError("API key for ApiKeyAuth not found.")

            elif isinstance(provider.auth, BasicAuth):
                auth = AiohttpBasicAuth(provider.auth.username, provider.auth.password)

            elif isinstance(provider.auth, OAuth2Auth):
                # OAuth2 tokens are always sent in the Authorization header.
                # Declared so cross-origin scrub recognises it.
                auth_header_names.append("Authorization")

        return auth, cookies, auth_header_names

    async def register_manual(self, caller, manual_call_template: CallTemplate) -> RegisterManualResult:
        """REQUIRED
        Register a manual and its tools from an SSE provider."""
        if not isinstance(manual_call_template, SseCallTemplate):
            raise ValueError("SSECommunicationProtocol can only be used with SSECallTemplate")

        try:
            url = manual_call_template.url

            # Security check: only HTTPS or loopback HTTP allowed for manual discovery.
            ensure_secure_url(url, context="manual discovery")

            logger.info(f"Discovering tools from '{manual_call_template.name}' (SSE) at {url}")
            
            # Use the provider's configuration (headers, auth, etc.)
            request_headers = manual_call_template.headers.copy() if manual_call_template.headers else {}
            body_content = None
            
            # Handle authentication
            query_params: Dict[str, Any] = {}
            auth, cookies, auth_header_names = self._apply_auth(manual_call_template, request_headers, query_params)

            # Handle OAuth2 separately as it's async
            if isinstance(manual_call_template.auth, OAuth2Auth):
                token = await self._handle_oauth2(manual_call_template.auth)
                request_headers["Authorization"] = f"Bearer {token}"
            
            # Handle body content if specified
            if manual_call_template.body_field:
                # For discovery, we typically don't have body content, but support it if needed
                body_content = None
            
            async with aiohttp.ClientSession() as session:
                # Set content-type header if body is provided and header not already set
                if body_content is not None and "Content-Type" not in request_headers:
                    request_headers["Content-Type"] = "application/json"
                
                # Prepare body content based on content type
                data = None
                json_data = None
                if body_content is not None:
                    if "application/json" in request_headers.get("Content-Type", ""):
                        json_data = body_content
                    else:
                        data = body_content
                
                # Re-validate every redirect hop. aiohttp's default
                # ``allow_redirects=True`` would otherwise let an
                # attacker-controlled discovery URL 302 us into an
                # internal service (GHSA-9qhg-99ww-9mqc).
                method = "GET"  # Default to GET for discovery
                async with safe_request_with_redirects(
                    session,
                    method,
                    url,
                    context="manual discovery",
                    headers=request_headers,
                    auth=auth,
                    params=query_params,
                    cookies=cookies,
                    json=json_data,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=10.0),
                    auth_header_names=auth_header_names,
                ) as response:
                    await raise_for_status_with_body(response)
                    response_data = await response.json()
                    utcp_manual = UtcpManualSerializer().validate_dict(response_data)
                    reject_remote_loopback_tool_urls(url, utcp_manual)
                    return RegisterManualResult(
                        success=True,
                        manual_call_template=manual_call_template,
                        manual=utcp_manual,
                        errors=[]
                    )
        except Exception as e:
            logger.error(f"Error discovering tools from '{manual_call_template.name}': {e}")
            return RegisterManualResult(
                success=False,
                manual_call_template=manual_call_template,
                manual=UtcpManual(manual_version="0.0.0", tools=[]),
                errors=[traceback.format_exc()]
            )

    async def deregister_manual(self, caller, manual_call_template: CallTemplate) -> None:
        """REQUIRED
        Deregister an SSE manual."""
        pass
    
    async def call_tool(self, caller, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        """REQUIRED
        Execute a tool call through SSE transport."""
        if not isinstance(tool_call_template, SseCallTemplate):
            raise ValueError("SSECommunicationProtocol can only be used with SSECallTemplate")
        
        event_list = []
        async for event in self.call_tool_streaming(caller, tool_name, tool_args, tool_call_template):
            event_list.append(event)
        return event_list
    
    async def call_tool_streaming(self, caller, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any, None]:
        """REQUIRED
        Execute a tool call through SSE transport with streaming."""
        if not isinstance(tool_call_template, SseCallTemplate):
            raise ValueError("SSECommunicationProtocol can only be used with SSECallTemplate")

        request_headers = tool_call_template.headers.copy() if tool_call_template.headers else {}
        body_content = None
        remaining_args = tool_args.copy()
        request_headers["Accept"] = "text/event-stream"

        if tool_call_template.header_fields:
            for field_name in tool_call_template.header_fields:
                if field_name in remaining_args:
                    request_headers[field_name] = str(remaining_args.pop(field_name))

        if tool_call_template.body_field and tool_call_template.body_field in remaining_args:
            body_content = remaining_args.pop(tool_call_template.body_field)

        # Build the URL with path parameters substituted
        url = self._build_url_with_path_params(tool_call_template.url, remaining_args)

        # Security check: re-validate the resolved URL before each invocation.
        # Defends against SSRF via attacker-controlled OpenAPI specs that point
        # ``servers[0].url`` at internal services. See issue #83.
        ensure_secure_url(url, context="tool invocation")

        # The rest of the arguments are query parameters
        query_params = remaining_args

        # Handle authentication
        # ``auth_header_names`` unused in the streaming path because
        # SSE handshake uses ``allow_redirects=False`` -- there is no
        # redirect chain to scrub. Reserved for future use if
        # streaming ever supports per-hop validation.
        auth, cookies, _auth_header_names = self._apply_auth(tool_call_template, request_headers, query_params)

        # Handle OAuth2 separately as it's async
        if isinstance(tool_call_template.auth, OAuth2Auth):
            token = await self._handle_oauth2(tool_call_template.auth)
            request_headers["Authorization"] = f"Bearer {token}"
        
        method = "POST" if body_content is not None else "GET"
        content_type = request_headers.get("Content-Type", "")
        data = body_content if "application/json" not in content_type else None
        json_data = body_content if "application/json" in content_type else None

        # Never re-send a request body: a reconnect re-issues the request, and for
        # a POST that would re-execute a possibly non-idempotent tool.
        reconnect = bool(tool_call_template.reconnect) and body_content is None
        if tool_call_template.reconnect and body_content is not None:
            logger.info(f"Reconnection is disabled for '{tool_call_template.name}' because the call sends a request body.")
        retry_delay_ms = tool_call_template.retry_timeout
        last_event_id: Optional[str] = None
        reconnect_attempts = 0
        provider_name = tool_call_template.name

        while True:
            attempt_headers = dict(request_headers)
            if last_event_id:
                # Let the server resume from where we left off (SSE spec). An empty
                # last event ID means "none": the header is not sent.
                attempt_headers["Last-Event-ID"] = last_event_id

            session = aiohttp.ClientSession()
            try:
                try:
                    # SSE handshake must not follow redirects: the streaming
                    # response has to stay open for the lifetime of the tool
                    # call, which is incompatible with the per-hop validator's
                    # release semantics, and SSE redirects are pathological in
                    # practice. Reject 3xx outright so an attacker-controlled
                    # endpoint cannot redirect the handshake into an internal
                    # service (GHSA-9qhg-99ww-9mqc).
                    # Bound the handshake only (until response headers arrive);
                    # the body read stays unbounded because a stream may be quiet.
                    response = await asyncio.wait_for(
                        session.request(
                            method, url, params=query_params, headers=attempt_headers,
                            auth=auth, cookies=cookies, json=json_data, data=data,
                            timeout=None, allow_redirects=False,
                        ),
                        timeout=self.HANDSHAKE_TIMEOUT_SECONDS,
                    )
                    if 300 <= response.status < 400:
                        response.release()
                        raise RuntimeError(
                            f"SSE endpoint at {url!r} returned a {response.status} "
                            f"redirect. Redirects are not followed during SSE "
                            f"handshakes; update the call template to point at "
                            f"the final URL directly."
                        )
                    # The error-body read is bounded like the handshake, so a server that
                    # answers 4xx/5xx and then stalls cannot hang the call either.
                    await asyncio.wait_for(raise_for_status_with_body(response), timeout=self.HANDSHAKE_TIMEOUT_SECONDS)
                    # Anything but an event stream would be parsed into silence: a
                    # JSON error document, say, yields zero events and a "successful" call.
                    content_type = response.headers.get("Content-Type", "")
                    # Compare the media type exactly (parameters such as charset allowed),
                    # so "text/event-stream-invalid" does not pass a substring check.
                    media_type = content_type.split(";", 1)[0].strip().lower()
                    if media_type != "text/event-stream":
                        response.release()
                        raise SseProtocolError(
                            f"Expected a text/event-stream response but got {content_type or 'no Content-Type'!r}"
                        )
                except SseProtocolError:
                    raise
                except Exception as e:
                    if reconnect_attempts == 0:
                        # The initial handshake failing (refused, timed out, non-2xx) is a
                        # definitive answer about the endpoint: fail fast, no retry.
                        logger.error(f"Error establishing SSE connection to '{provider_name}': {e}")
                        raise
                    # A reconnect handshake failing is part of the outage we are riding
                    # out (the server may still be restarting): count it and try again.
                    reconnect_attempts += 1
                    if reconnect_attempts > self.MAX_RECONNECT_ATTEMPTS:
                        logger.error(f"SSE reconnect to '{provider_name}' failed and attempts are exhausted: {e}")
                        raise
                    delay_ms = min(retry_delay_ms, self.MAX_RECONNECT_DELAY_MS)
                    logger.warning(
                        f"SSE reconnect to '{provider_name}' failed ({e}); retrying in {delay_ms} ms "
                        f"(attempt {reconnect_attempts}/{self.MAX_RECONNECT_ATTEMPTS})"
                    )
                    await asyncio.sleep(delay_ms / 1000)
                    continue

                try:
                    async for event in self._iter_sse_events(response):
                        # Per the SSE spec an id containing NUL is ignored, and an empty id
                        # resets the last event ID.
                        if event.get("id") is not None and "\x00" not in event["id"]:
                            last_event_id = event["id"]
                        if event.get("retry") is not None:
                            retry_delay_ms = event["retry"]
                        if "data" not in event:
                            continue
                        # An event block without an ``event:`` field has the type "message".
                        if tool_call_template.event_type and (event.get("event") or "message") != tool_call_template.event_type:
                            continue
                        yield self._parse_event_data(event["data"])
                    # The server ended the stream cleanly: the tool call is complete.
                    return
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    reconnect_attempts += 1
                    if not reconnect or reconnect_attempts > self.MAX_RECONNECT_ATTEMPTS:
                        logger.error(f"SSE connection to '{provider_name}' lost and not reconnecting: {e}")
                        raise
                    logger.warning(
                        f"SSE connection to '{provider_name}' lost ({e}); reconnecting in "
                        f"{min(retry_delay_ms, self.MAX_RECONNECT_DELAY_MS)} ms "
                        f"(attempt {reconnect_attempts}/{self.MAX_RECONNECT_ATTEMPTS})"
                    )
            finally:
                # Always release the connection, whether the stream completed, failed,
                # or the consumer stopped iterating early.
                if not session.closed:
                    await session.close()

            await asyncio.sleep(min(retry_delay_ms, self.MAX_RECONNECT_DELAY_MS) / 1000)

    async def _iter_sse_events(self, response: aiohttp.ClientResponse) -> AsyncIterator[Dict[str, Any]]:
        """Parse the SSE wire format and yield one dict per event block.

        Each dict may contain ``event``, ``id``, ``retry`` (int) and ``data`` (str, with
        multi-line data joined by newlines). Blocks that only carry ``id``/``retry``
        are yielded too (without ``data``) so the caller can track reconnection
        state; comment-only blocks are skipped.
        """
        buffer = ""

        def flush(event_string: str):
            if not event_string.strip():
                return None
            current_event: Dict[str, Any] = {}
            data_lines: List[str] = []
            for line in event_string.split('\n'):
                if line.startswith(':'):
                    continue  # comment / keep-alive
                if ':' in line:
                    field, value = line.split(':', 1)
                    if value.startswith(' '):
                        value = value[1:]
                else:
                    field, value = line, ''
                if field == 'event':
                    current_event['event'] = value
                elif field == 'data':
                    data_lines.append(value)
                elif field == 'id':
                    current_event['id'] = value
                elif field == 'retry':
                    # Spec: only a value made of ASCII digits sets the reconnection time.
                    # Anything longer than 18 digits is absurd (and would be capped anyway);
                    # bounding the length keeps the conversion cheap whatever the interpreter.
                    if value.isascii() and value.isdigit() and len(value) <= 18:
                        current_event['retry'] = int(value)
            if data_lines:
                current_event['data'] = '\n'.join(data_lines)
            return current_event or None

        # Incremental decoding: a multi-byte UTF-8 character may straddle two chunks.
        decoder = codecs.getincrementaldecoder("utf-8")()
        # A "\r" that ended the previous chunk is held back until the next chunk
        # shows whether a "\n" follows; otherwise a CRLF split across two reads
        # would become two LFs and dispatch an event early.
        pending_cr = False

        def normalise(text: str) -> str:
            nonlocal pending_cr
            if pending_cr:
                text = "\r" + text
                pending_cr = False
            if text.endswith("\r"):
                text = text[:-1]
                pending_cr = True
            # Normalise CRLF / CR line endings so the event delimiter is always "\n\n".
            return text.replace("\r\n", "\n").replace("\r", "\n")

        async for chunk in response.content.iter_any():
            buffer += normalise(decoder.decode(chunk))
            while "\n\n" in buffer:
                event_string, buffer = buffer.split("\n\n", 1)
                event = flush(event_string)
                if event is not None:
                    yield event
            if len(buffer) > self.MAX_EVENT_BUFFER_CHARS:
                raise SseProtocolError(
                    f"SSE event exceeded {self.MAX_EVENT_BUFFER_CHARS} characters without a blank-line delimiter"
                )

        # At end of stream, a held-back CR is a real line terminator and may
        # complete the closing blank line of the last event. Dispatch whatever is
        # fully delimited; per spec, an event still incomplete after that (no
        # final blank line) is discarded.
        buffer += normalise(decoder.decode(b"", final=True))
        if pending_cr:
            buffer += "\n"
            pending_cr = False
        while "\n\n" in buffer:
            event_string, buffer = buffer.split("\n\n", 1)
            event = flush(event_string)
            if event is not None:
                yield event
        # The residual (discarded) buffer is still subject to the cap, so an
        # over-limit malformed stream fails the same way at end of stream.
        if len(buffer) > self.MAX_EVENT_BUFFER_CHARS:
            raise SseProtocolError(
                f"SSE event exceeded {self.MAX_EVENT_BUFFER_CHARS} characters without a blank-line delimiter"
            )

    @staticmethod
    def _parse_event_data(data: str) -> Any:
        """Return the JSON-decoded payload when possible, otherwise the raw string."""
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data

    async def _handle_oauth2(self, auth_details: OAuth2Auth) -> str:
        """Handle OAuth2 client credentials flow, trying both body and
        auth header methods.

        Validates the token URL before posting credentials so an
        attacker-controlled OpenAPI spec cannot redirect ``client_id`` /
        ``client_secret`` exfiltration through this protocol
        (GHSA-8cp3-qxj6-px34). The redirect helper also blocks the
        post-issue redirect SSRF (GHSA-9qhg-99ww-9mqc) on the token
        endpoint itself.
        """
        client_id = auth_details.client_id
        if client_id in self._oauth_tokens:
            return self._oauth_tokens[client_id]["access_token"]

        # Reject obviously-internal or plain-HTTP non-loopback token
        # endpoints before any credential bytes leave the process.
        ensure_secure_url(auth_details.token_url, context="OAuth2 token URL")

        async with aiohttp.ClientSession() as session:
            try: # Method 1: Credentials in body
                body_data = {'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': auth_details.client_secret, 'scope': auth_details.scope}
                async with safe_request_with_redirects(
                    session,
                    "POST",
                    auth_details.token_url,
                    context="OAuth2 token fetch",
                    data=body_data,
                ) as response:
                    response.raise_for_status()
                    token_response = await response.json()
                    self._oauth_tokens[client_id] = token_response
                    return token_response["access_token"]
            except aiohttp.ClientError as e:
                logger.error(f"OAuth2 with body failed: {e}. Trying Basic Auth.")

            try: # Method 2: Credentials in header
                header_auth = aiohttp.BasicAuth(client_id, auth_details.client_secret)
                header_data = {'grant_type': 'client_credentials', 'scope': auth_details.scope}
                async with safe_request_with_redirects(
                    session,
                    "POST",
                    auth_details.token_url,
                    context="OAuth2 token fetch",
                    data=header_data,
                    auth=header_auth,
                ) as response:
                    response.raise_for_status()
                    token_response = await response.json()
                    self._oauth_tokens[client_id] = token_response
                    return token_response["access_token"]
            except aiohttp.ClientError as e:
                logger.error(f"OAuth2 with header failed: {e}")
                raise e
    
    def _build_url_with_path_params(self, url_template: str, tool_args: Dict[str, Any]) -> str:
        """Build URL by substituting path parameters from arguments.
        
        Args:
            url_template: URL template with path parameters in {param_name} format
            tool_args: Dictionary of arguments that will be modified to remove used path parameters
            
        Returns:
            URL with path parameters substituted
            
        Example:
            url_template = "https://api.example.com/users/{user_id}/posts/{post_id}"
            tool_args = {"user_id": "123", "post_id": "456", "limit": "10"}
            Returns: "https://api.example.com/users/123/posts/456"
            And modifies tool_args to: {"limit": "10"}
        """
        # Find all path parameters in the URL template
        path_params = re.findall(r'\{([^}]+)\}', url_template)
        
        url = url_template
        for param_name in path_params:
            if param_name in tool_args:
                # Replace the parameter in the URL
                # URL-encode the parameter value to prevent path injection
                param_value = quote(str(tool_args[param_name]), safe="")
                url = url.replace(f'{{{param_name}}}', param_value)
                # Remove the parameter from arguments so it's not used as a query parameter
                tool_args.pop(param_name)
            else:
                raise ValueError(f"Missing required path parameter: {param_name}")
        
        # Check if there are any unreplaced path parameters
        remaining_params = re.findall(r'\{([^}]+)\}', url)
        if remaining_params:
            raise ValueError(f"Missing required path parameters: {remaining_params}")
        
        return url
