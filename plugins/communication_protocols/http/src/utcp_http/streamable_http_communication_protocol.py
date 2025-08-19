from typing import Dict, Any, List, Optional, Callable, AsyncIterator, Tuple, AsyncGenerator
import aiohttp
import json
import re
from urllib.parse import quote

from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool
from utcp.data.utcp_manual import UtcpManual, UtcpManualSerializer
from utcp.data.register_manual_response import RegisterManualResult
from utcp.data.auth_implementations import ApiKeyAuth
from utcp.data.auth_implementations import BasicAuth
from utcp.data.auth_implementations import OAuth2Auth
from utcp_http.streamable_http_call_template import StreamableHttpCallTemplate
from aiohttp import ClientSession, BasicAuth as AiohttpBasicAuth, ClientResponse
import logging

logger = logging.getLogger(__name__)

class StreamableHttpCommunicationProtocol(CommunicationProtocol):
    """Streamable HTTP communication protocol implementation for UTCP client.
    
    Handles HTTP streaming with chunked transfer encoding for real-time data.
    """

    def __init__(self):
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}

    def _apply_auth(self, provider: StreamableHttpCallTemplate, headers: Dict[str, str], query_params: Dict[str, Any]) -> tuple:
        """Apply authentication to the request based on the provider's auth configuration.
        
        Returns:
            tuple: (auth_obj, cookies) where auth_obj is for aiohttp basic auth and cookies is a dict
        """
        auth = None
        cookies = {}
        
        if provider.auth:
            if isinstance(provider.auth, ApiKeyAuth):
                if provider.auth.api_key:
                    if provider.auth.location == "header":
                        headers[provider.auth.var_name] = provider.auth.api_key
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
                # OAuth2 tokens are always sent in the Authorization header
                # We'll handle this separately since it requires async token retrieval
                pass
        
        return auth, cookies

    async def close(self):
        """Close all active connections and clear internal state."""
        logger.info("Closing StreamableHttpCommunicationProtocol.")
        self._oauth_tokens.clear()

    async def register_manual(self, caller, manual_call_template: CallTemplate) -> RegisterManualResult:
        """Register a manual and its tools from a StreamableHttp provider."""
        if not isinstance(manual_call_template, StreamableHttpCallTemplate):
            raise ValueError("StreamableHttpCommunicationProtocol can only be used with StreamableHttpCallTemplate")

        url = manual_call_template.url
        
        # Security check: Enforce HTTPS or localhost to prevent MITM attacks
        if not (url.startswith("https://") or url.startswith("http://localhost") or url.startswith("http://127.0.0.1")):
            raise ValueError(
                f"Security error: URL must use HTTPS or start with 'http://localhost' or 'http://127.0.0.1'. Got: {url}. "
                "Non-secure URLs are vulnerable to man-in-the-middle attacks."
            )
            
        logger.info(f"Discovering tools from '{manual_call_template.name}' (HTTP Stream) at {url}")

        try:
            # Use the template's configuration (headers, auth, etc.)
            request_headers = manual_call_template.headers.copy() if manual_call_template.headers else {}
            body_content = None
            
            # Handle authentication
            query_params: Dict[str, Any] = {}
            auth, cookies = self._apply_auth(manual_call_template, request_headers, query_params)
            
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
                    request_headers["Content-Type"] = manual_call_template.content_type
                
                # Prepare body content based on content type
                data = None
                json_data = None
                if body_content is not None:
                    if "application/json" in request_headers.get("Content-Type", ""):
                        json_data = body_content
                    else:
                        data = body_content
                
                # Make the request with the template's HTTP method
                method = manual_call_template.http_method.lower()
                request_method = getattr(session, method)
                
                async with request_method(
                    url,
                    headers=request_headers,
                    auth=auth,
                    params=query_params,
                    cookies=cookies,
                    json=json_data,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=10.0)
                ) as response:
                    response.raise_for_status()
                    response_data = await response.json()
                    utcp_manual = UtcpManualSerializer().validate_dict(response_data)
                    return RegisterManualResult(
                        success=True,
                        manual_call_template=manual_call_template,
                        manual=utcp_manual,
                        errors=[]
                    )
        except aiohttp.ClientResponseError as e:
            error_msg = f"Error discovering tools from '{manual_call_template.name}': {e.status}, message='{e.message}', url='{e.request_info.url}'"
            logger.error(error_msg)
            return RegisterManualResult(
                success=False,
                manual_call_template=manual_call_template,
                manual=UtcpManual(manual_version="0.0.0", tools=[]),
                errors=[error_msg]
            )
        except (json.JSONDecodeError, aiohttp.ClientError) as e:
            error_msg = f"Error processing request for '{manual_call_template.name}': {e}"
            logger.error(error_msg)
            return RegisterManualResult(
                success=False,
                manual_call_template=manual_call_template,
                manual=UtcpManual(manual_version="0.0.0", tools=[]),
                errors=[error_msg]
            )
        except Exception as e:
            error_msg = f"An unexpected error occurred while discovering tools from '{manual_call_template.name}': {e}"
            logger.error(error_msg)
            return RegisterManualResult(
                success=False,
                manual_call_template=manual_call_template,
                manual=UtcpManual(manual_version="0.0.0", tools=[]),
                errors=[error_msg]
            )

    async def deregister_manual(self, caller, manual_call_template: CallTemplate) -> None:
        """Deregister a StreamableHttp manual. This is a no-op for the stateless streamable HTTP protocol."""
        logger.info(f"Deregistering manual '{manual_call_template.name}'. No active connection to close.")

    async def call_tool(self, caller, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        """Execute a tool call through StreamableHttp transport."""
        if not isinstance(tool_call_template, StreamableHttpCallTemplate):
            raise ValueError("StreamableHttpCommunicationProtocol can only be used with StreamableHttpCallTemplate")
        
        is_bytes = False
        chunk_list = []
        chunk_bytes = b''
        async for chunk in self.call_tool_streaming(caller, tool_name, tool_args, tool_call_template):
            if isinstance(chunk, bytes):
                is_bytes = True
                chunk_bytes += chunk
            else:
                chunk_list.append(chunk)
        if is_bytes:
            return chunk_bytes
        return chunk_list
    
    async def call_tool_streaming(self, caller, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any, None]:
        """Execute a tool call through StreamableHttp transport with streaming."""
        if not isinstance(tool_call_template, StreamableHttpCallTemplate):
            raise ValueError("StreamableHttpCommunicationProtocol can only be used with StreamableHttpCallTemplate")

        request_headers = tool_call_template.headers.copy() if tool_call_template.headers else {}
        body_content = None
        remaining_args = tool_args.copy()

        if tool_call_template.header_fields:
            for field_name in tool_call_template.header_fields:
                if field_name in remaining_args:
                    request_headers[field_name] = str(remaining_args.pop(field_name))

        if tool_call_template.body_field and tool_call_template.body_field in remaining_args:
            body_content = remaining_args.pop(tool_call_template.body_field)

        # Build the URL with path parameters substituted
        url = self._build_url_with_path_params(tool_call_template.url, remaining_args)
        
        # The rest of the arguments are query parameters
        query_params = remaining_args

        # Handle authentication
        auth_handler, cookies = self._apply_auth(tool_call_template, request_headers, query_params)

        # Handle OAuth2 separately as it's async
        if isinstance(tool_call_template.auth, OAuth2Auth):
            token = await self._handle_oauth2(tool_call_template.auth)
            request_headers["Authorization"] = f"Bearer {token}"

        session = None
        response = None
        try:
            session = ClientSession()
            timeout_seconds = tool_call_template.timeout / 1000 if tool_call_template.timeout else 60.0
            timeout = aiohttp.ClientTimeout(total=timeout_seconds)

            data = None
            json_data = None
            if body_content is not None:
                if "Content-Type" not in request_headers:
                    request_headers["Content-Type"] = tool_call_template.content_type
                if "application/json" in request_headers.get("Content-Type", ""):
                    json_data = body_content
                else:
                    data = body_content

            response = await session.request(
                method=tool_call_template.http_method,
                url=url,
                params=query_params,
                headers=request_headers,
                auth=auth_handler,
                cookies=cookies,
                json=json_data,
                data=data,
                timeout=timeout
            )
            response.raise_for_status()

            async for chunk in self._process_http_stream(response, tool_call_template.chunk_size, tool_call_template.name):
                yield chunk

        except Exception as e:
            logger.error(f"Error during HTTP stream for '{tool_call_template.name}': {e}")
            raise
        finally:
            if response and not response.closed:
                response.close()
            if session and not session.closed:
                await session.close()

    async def _process_http_stream(self, response: ClientResponse, chunk_size: Optional[int], provider_name: str) -> AsyncIterator[Any]:
        """Process the HTTP stream and yield chunks based on content type."""
        try:
            content_type = response.headers.get('Content-Type', '')

            if 'application/x-ndjson' in content_type:
                async for line in response.content:
                    if line.strip():
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            logger.error(f"Error parsing NDJSON line for '{provider_name}': {line[:100]}")
                            yield line # Yield raw line on error
            elif 'application/octet-stream' in content_type:
                async for chunk in response.content.iter_chunked(chunk_size or 8192):
                    if chunk:
                        yield chunk
            elif 'application/json' in content_type:
                # Buffer the entire response for a single JSON object
                buffer = b''
                async for chunk in response.content.iter_any():
                    buffer += chunk
                if buffer:
                    try:
                        yield json.loads(buffer)
                    except json.JSONDecodeError:
                        logger.error(f"Error parsing JSON response for '{provider_name}': {buffer[:100]}")
                        yield buffer # Yield raw buffer on error
            else:
                # Default to binary chunk streaming for unknown content types
                async for chunk in response.content.iter_chunked(chunk_size or 8192):
                    if chunk:
                        yield chunk
        except Exception as e:
            logger.error(f"Error processing HTTP stream for '{provider_name}': {e}")
            raise
        finally:
            # The response and session are managed by the `call_tool_streaming` method.
            pass

    async def _handle_oauth2(self, auth_details: OAuth2Auth) -> str:
        """Handles OAuth2 client credentials flow, trying both body and auth header methods."""
        client_id = auth_details.client_id
        if client_id in self._oauth_tokens:
            return self._oauth_tokens[client_id]["access_token"]

        async with aiohttp.ClientSession() as session:
            # Method 1: Credentials in body
            try:
                logger.info(f"Attempting OAuth2 token fetch for '{client_id}' with credentials in body.")
                async with session.post(auth_details.token_url, data={'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': auth_details.client_secret, 'scope': auth_details.scope}) as response:
                    response.raise_for_status()
                    token_data = await response.json()
                    self._oauth_tokens[client_id] = token_data
                    return token_data['access_token']
            except aiohttp.ClientError as e:
                logger.error(f"OAuth2 with credentials in body failed: {e}. Trying Basic Auth header.")

            # Method 2: Credentials as Basic Auth header
            try:
                logger.info(f"Attempting OAuth2 token fetch for '{client_id}' with Basic Auth header.")
                auth = AiohttpBasicAuth(client_id, auth_details.client_secret)
                async with session.post(auth_details.token_url, data={'grant_type': 'client_credentials', 'scope': auth_details.scope}, auth=auth) as response:
                    response.raise_for_status()
                    token_data = await response.json()
                    self._oauth_tokens[client_id] = token_data
                    return token_data['access_token']
            except aiohttp.ClientError as e:
                logger.error(f"OAuth2 with Basic Auth header also failed: {e}")
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
