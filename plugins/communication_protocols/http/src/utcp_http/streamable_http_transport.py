from typing import Dict, Any, List, Optional, Callable, AsyncIterator, Tuple
import aiohttp
import json
import re

from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.shared.provider import Provider, StreamableHttpProvider
from utcp.shared.tool import Tool
from utcp.shared.utcp_manual import UtcpManual
from utcp.shared.auth import ApiKeyAuth, BasicAuth, OAuth2Auth
from aiohttp import ClientSession, BasicAuth as AiohttpBasicAuth, ClientResponse


class StreamableHttpClientTransport(ClientTransportInterface):
    """Client transport implementation for HTTP streaming (chunked transfer encoding) providers using aiohttp."""

    def __init__(self, logger: Optional[Callable[[str, Any], None]] = None):
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}
        self._log = logger or (lambda *args, **kwargs: None)
        self._active_connections: Dict[str, Tuple[ClientResponse, ClientSession]] = {}

    def _apply_auth(self, provider: StreamableHttpProvider, headers: Dict[str, str], query_params: Dict[str, Any]) -> tuple:
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
                    self._log("API key not found for ApiKeyAuth.", error=True)
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
        self._log("Closing all active HTTP stream connections.")
        for provider_name, (response, session) in list(self._active_connections.items()):
            self._log(f"Closing connection for provider: {provider_name}")
            if not response.closed:
                response.close()  # Close the response
            if not session.closed:
                await session.close()
        self._active_connections.clear()
        self._oauth_tokens.clear()

    async def register_tool_provider(self, manual_provider: Provider) -> List[Tool]:
        """Discover tools from a StreamableHttp provider."""
        if not isinstance(manual_provider, StreamableHttpProvider):
            raise ValueError("StreamableHttpClientTransport can only be used with StreamableHttpProvider")

        url = manual_provider.url
        
        # Security check: Enforce HTTPS or localhost to prevent MITM attacks
        if not (url.startswith("https://") or url.startswith("http://localhost") or url.startswith("http://127.0.0.1")):
            raise ValueError(
                f"Security error: URL must use HTTPS or start with 'http://localhost' or 'http://127.0.0.1'. Got: {url}. "
                "Non-secure URLs are vulnerable to man-in-the-middle attacks."
            )
            
        self._log(f"Discovering tools from '{manual_provider.name}' (HTTP Stream) at {url}")

        try:
            # Use the provider's configuration (headers, auth, etc.)
            request_headers = manual_provider.headers.copy() if manual_provider.headers else {}
            body_content = None
            
            # Handle authentication
            query_params: Dict[str, Any] = {}
            auth, cookies = self._apply_auth(manual_provider, request_headers, query_params)
            
            # Handle OAuth2 separately as it's async
            if isinstance(manual_provider.auth, OAuth2Auth):
                token = await self._handle_oauth2(manual_provider.auth)
                request_headers["Authorization"] = f"Bearer {token}"
            
            # Handle body content if specified
            if manual_provider.body_field:
                # For discovery, we typically don't have body content, but support it if needed
                body_content = None
            
            async with aiohttp.ClientSession() as session:
                # Set content-type header if body is provided and header not already set
                if body_content is not None and "Content-Type" not in request_headers:
                    request_headers["Content-Type"] = manual_provider.content_type
                
                # Prepare body content based on content type
                data = None
                json_data = None
                if body_content is not None:
                    if "application/json" in request_headers.get("Content-Type", ""):
                        json_data = body_content
                    else:
                        data = body_content
                
                # Make the request with the provider's HTTP method
                method = manual_provider.http_method.lower()
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
                    utcp_manual = UtcpManual(**response_data)
                    return utcp_manual.tools
        except aiohttp.ClientResponseError as e:
            self._log(f"Error discovering tools from '{manual_provider.name}': {e.status}, message='{e.message}', url='{e.request_info.url}'", error=True)
            return []
        except (json.JSONDecodeError, aiohttp.ClientError) as e:
            self._log(f"Error processing request for '{manual_provider.name}': {e}", error=True)
            return []
        except Exception as e:
            self._log(f"An unexpected error occurred while discovering tools from '{manual_provider.name}': {e}", error=True)
            return []

    async def deregister_tool_provider(self, manual_provider: Provider) -> None:
        """Deregister a StreamableHttp provider and close any active connections."""
        if not isinstance(manual_provider, StreamableHttpProvider):
            return

        if manual_provider.name in self._active_connections:
            self._log(f"Closing active HTTP stream connection for provider '{manual_provider.name}'")
            response, session = self._active_connections.pop(manual_provider.name)
            if not response.closed:
                response.close()
            if not session.closed:
                await session.close()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], tool_provider: Provider) -> AsyncIterator[Any]:
        """Calls a tool on a StreamableHttp provider and returns an async iterator for the response chunks."""
        if not isinstance(tool_provider, StreamableHttpProvider):
            raise ValueError("StreamableHttpClientTransport can only be used with StreamableHttpProvider")

        request_headers = tool_provider.headers.copy() if tool_provider.headers else {}
        body_content = None
        remaining_args = arguments.copy()

        if tool_provider.header_fields:
            for field_name in tool_provider.header_fields:
                if field_name in remaining_args:
                    request_headers[field_name] = str(remaining_args.pop(field_name))

        if tool_provider.body_field and tool_provider.body_field in remaining_args:
            body_content = remaining_args.pop(tool_provider.body_field)

        # Build the URL with path parameters substituted
        url = self._build_url_with_path_params(tool_provider.url, remaining_args)
        
        # The rest of the arguments are query parameters
        query_params = remaining_args

        # Handle authentication
        auth_handler, cookies = self._apply_auth(tool_provider, request_headers, query_params)

        # Handle OAuth2 separately as it's async
        if isinstance(tool_provider.auth, OAuth2Auth):
            token = await self._handle_oauth2(tool_provider.auth)
            request_headers["Authorization"] = f"Bearer {token}"

        session = ClientSession()
        try:
            timeout_seconds = tool_provider.timeout / 1000 if tool_provider.timeout else 60.0
            timeout = aiohttp.ClientTimeout(total=timeout_seconds)

            data = None
            json_data = None
            if body_content is not None:
                if "Content-Type" not in request_headers:
                    request_headers["Content-Type"] = tool_provider.content_type
                if "application/json" in request_headers.get("Content-Type", ""):
                    json_data = body_content
                else:
                    data = body_content

            response = await session.request(
                method=tool_provider.http_method,
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

            self._active_connections[tool_provider.name] = (response, session)
            return self._process_http_stream(response, tool_provider.chunk_size, tool_provider.name)

        except Exception as e:
            await session.close()
            self._log(f"Error establishing HTTP stream connection to '{tool_provider.name}': {e}", error=True)
            raise

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
                            self._log(f"Error parsing NDJSON line for '{provider_name}': {line[:100]}", error=True)
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
                        self._log(f"Error parsing JSON response for '{provider_name}': {buffer[:100]}", error=True)
                        yield buffer # Yield raw buffer on error
            else:
                # Default to binary chunk streaming for unknown content types
                async for chunk in response.content.iter_chunked(chunk_size or 8192):
                    if chunk:
                        yield chunk
        except Exception as e:
            self._log(f"Error processing HTTP stream for '{provider_name}': {e}", error=True)
            raise
        finally:
            # The session is closed later by deregister_tool_provider or close()
            if provider_name in self._active_connections:
                response, _ = self._active_connections[provider_name]
                if not response.closed:
                    response.close()

    async def _handle_oauth2(self, auth_details: OAuth2Auth) -> str:
        """Handles OAuth2 client credentials flow, trying both body and auth header methods."""
        client_id = auth_details.client_id
        if client_id in self._oauth_tokens:
            return self._oauth_tokens[client_id]["access_token"]

        async with aiohttp.ClientSession() as session:
            # Method 1: Credentials in body
            try:
                self._log(f"Attempting OAuth2 token fetch for '{client_id}' with credentials in body.")
                async with session.post(auth_details.token_url, data={'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': auth_details.client_secret, 'scope': auth_details.scope}) as response:
                    response.raise_for_status()
                    token_data = await response.json()
                    self._oauth_tokens[client_id] = token_data
                    return token_data['access_token']
            except aiohttp.ClientError as e:
                self._log(f"OAuth2 with credentials in body failed: {e}. Trying Basic Auth header.")

            # Method 2: Credentials as Basic Auth header
            try:
                self._log(f"Attempting OAuth2 token fetch for '{client_id}' with Basic Auth header.")
                auth = AiohttpBasicAuth(client_id, auth_details.client_secret)
                async with session.post(auth_details.token_url, data={'grant_type': 'client_credentials', 'scope': auth_details.scope}, auth=auth) as response:
                    response.raise_for_status()
                    token_data = await response.json()
                    self._oauth_tokens[client_id] = token_data
                    return token_data['access_token']
            except aiohttp.ClientError as e:
                self._log(f"OAuth2 with Basic Auth header also failed: {e}", error=True)
                raise e
    
    def _build_url_with_path_params(self, url_template: str, arguments: Dict[str, Any]) -> str:
        """Build URL by substituting path parameters from arguments.
        
        Args:
            url_template: URL template with path parameters in {param_name} format
            arguments: Dictionary of arguments that will be modified to remove used path parameters
            
        Returns:
            URL with path parameters substituted
            
        Example:
            url_template = "https://api.example.com/users/{user_id}/posts/{post_id}"
            arguments = {"user_id": "123", "post_id": "456", "limit": "10"}
            Returns: "https://api.example.com/users/123/posts/456"
            And modifies arguments to: {"limit": "10"}
        """
        # Find all path parameters in the URL template
        path_params = re.findall(r'\{([^}]+)\}', url_template)
        
        url = url_template
        for param_name in path_params:
            if param_name in arguments:
                # Replace the parameter in the URL
                param_value = str(arguments[param_name])
                url = url.replace(f'{{{param_name}}}', param_value)
                # Remove the parameter from arguments so it's not used as a query parameter
                arguments.pop(param_name)
            else:
                raise ValueError(f"Missing required path parameter: {param_name}")
        
        # Check if there are any unreplaced path parameters
        remaining_params = re.findall(r'\{([^}]+)\}', url)
        if remaining_params:
            raise ValueError(f"Missing required path parameters: {remaining_params}")
        
        return url
