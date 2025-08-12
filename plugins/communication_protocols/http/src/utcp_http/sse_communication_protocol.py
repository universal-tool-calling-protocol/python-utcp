from typing import Dict, Any, List, Optional, Callable, AsyncIterator
import aiohttp
import json
import asyncio
import re
import base64

from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.shared.provider import Provider, SSEProvider
from utcp.shared.tool import Tool
from utcp.shared.utcp_manual import UtcpManual
from utcp.shared.auth import ApiKeyAuth, BasicAuth, OAuth2Auth
from aiohttp import ClientSession, BasicAuth as AiohttpBasicAuth


class SSEClientTransport(ClientTransportInterface):
    """Client transport implementation for Server-Sent Events providers."""

    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}
        self._log = logger or (lambda *args, **kwargs: None)
        self._active_connections: Dict[str, tuple[aiohttp.ClientResponse, aiohttp.ClientSession]] = {}

    def _apply_auth(self, provider: SSEProvider, headers: Dict[str, str], query_params: Dict[str, Any]) -> tuple:
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

    async def register_tool_provider(self, manual_provider: Provider) -> List[Tool]:
        """Discover tools from an SSE provider."""
        if not isinstance(manual_provider, SSEProvider):
            raise ValueError("SSEClientTransport can only be used with SSEProvider")

        try:
            url = manual_provider.url
            
            # Security check: Enforce HTTPS or localhost to prevent MITM attacks
            if not (url.startswith("https://") or url.startswith("http://localhost") or url.startswith("http://127.0.0.1")):
                raise ValueError(
                    f"Security error: URL must use HTTPS or start with 'http://localhost' or 'http://127.0.0.1'. Got: {url}. "
                    "Non-secure URLs are vulnerable to man-in-the-middle attacks."
                )
                
            self._log(f"Discovering tools from '{manual_provider.name}' (SSE) at {url}")
            
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
                    request_headers["Content-Type"] = "application/json"
                
                # Prepare body content based on content type
                data = None
                json_data = None
                if body_content is not None:
                    if "application/json" in request_headers.get("Content-Type", ""):
                        json_data = body_content
                    else:
                        data = body_content
                
                # Make the request (typically GET for discovery, but respect configuration)
                method = "GET"  # Default to GET for discovery
                request_method = getattr(session, method.lower())
                
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
        except Exception as e:
            self._log(f"Error discovering tools from '{manual_provider.name}': {e}", error=True)
            return []

    async def deregister_tool_provider(self, manual_provider: Provider) -> None:
        """Deregister an SSE provider and close any active connections."""
        if manual_provider.name in self._active_connections:
            self._log(f"Closing active SSE connection for provider '{manual_provider.name}'")
            response, session = self._active_connections.pop(manual_provider.name)
            response.close()
            await session.close()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], tool_provider: Provider) -> AsyncIterator[Any]:
        """Calls a tool on an SSE provider and returns an async iterator for the events."""
        if not isinstance(tool_provider, SSEProvider):
            raise ValueError("SSEClientTransport can only be used with SSEProvider")

        request_headers = tool_provider.headers.copy() if tool_provider.headers else {}
        body_content = None
        remaining_args = arguments.copy()
        request_headers["Accept"] = "text/event-stream"

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
        auth, cookies = self._apply_auth(tool_provider, request_headers, query_params)

        # Handle OAuth2 separately as it's async
        if isinstance(tool_provider.auth, OAuth2Auth):
            token = await self._handle_oauth2(tool_provider.auth)
            request_headers["Authorization"] = f"Bearer {token}"
        
        session = aiohttp.ClientSession()
        try:
            method = "POST" if body_content is not None else "GET"
            data = body_content if "application/json" not in request_headers.get("Content-Type", "") else None
            json_data = body_content if "application/json" in request_headers.get("Content-Type", "") else None

            response = await session.request(
                method, url, params=query_params, headers=request_headers,
                auth=auth, cookies=cookies, json=json_data, data=data, timeout=None
            )
            response.raise_for_status()
            self._active_connections[tool_provider.name] = (response, session)
            return self._process_sse_stream(response, tool_provider.event_type)
        except Exception as e:
            await session.close()
            self._log(f"Error establishing SSE connection to '{tool_provider.name}': {e}", error=True)
            raise

    async def _process_sse_stream(self, response: aiohttp.ClientResponse, event_type=None):
        """Process the SSE stream and yield events."""
        buffer = ""
        try:
            async for chunk in response.content.iter_any():
                buffer += chunk.decode('utf-8')
                while '\n\n' in buffer:
                    event_string, buffer = buffer.split('\n\n', 1)
                    
                    # Ignore empty event strings
                    if not event_string.strip():
                        continue

                    # Process the event string
                    lines = event_string.split('\n')
                    current_event = {}
                    data_lines = []
                    for line in lines:
                        if line.startswith(':'):
                            continue # It's a comment
                        
                        if ':' in line:
                            field, value = line.split(':', 1)
                            value = value.lstrip()
                            if field == 'event':
                                current_event['event'] = value
                            elif field == 'data':
                                data_lines.append(value)
                            elif field == 'id':
                                current_event['id'] = value
                            elif field == 'retry':
                                try:
                                    current_event['retry'] = int(value)
                                except ValueError:
                                    pass
                    
                    if not data_lines:
                        continue

                    current_event['data'] = '\n'.join(data_lines)

                    if event_type and current_event.get('event') != event_type:
                        continue

                    try:
                        yield json.loads(current_event['data'])
                    except json.JSONDecodeError:
                        yield current_event['data']
        except Exception as e:
            self._log(f"Error processing SSE stream: {e}", error=True)
            raise
        finally:
            pass # Session is managed and closed by deregister_tool_provider

    async def _handle_oauth2(self, auth_details: OAuth2Auth) -> str:
        """Handles OAuth2 client credentials flow, trying both body and auth header methods."""
        client_id = auth_details.client_id
        if client_id in self._oauth_tokens:
            return self._oauth_tokens[client_id]["access_token"]

        async with aiohttp.ClientSession() as session:
            try: # Method 1: Credentials in body
                body_data = {'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': auth_details.client_secret, 'scope': auth_details.scope}
                async with session.post(auth_details.token_url, data=body_data) as response:
                    response.raise_for_status()
                    token_response = await response.json()
                    self._oauth_tokens[client_id] = token_response
                    return token_response["access_token"]
            except aiohttp.ClientError as e:
                self._log(f"OAuth2 with body failed: {e}. Trying Basic Auth.")
            
            try: # Method 2: Credentials in header
                header_auth = aiohttp.BasicAuth(client_id, auth_details.client_secret)
                header_data = {'grant_type': 'client_credentials', 'scope': auth_details.scope}
                async with session.post(auth_details.token_url, data=header_data, auth=header_auth) as response:
                    response.raise_for_status()
                    token_response = await response.json()
                    self._oauth_tokens[client_id] = token_response
                    return token_response["access_token"]
            except aiohttp.ClientError as e:
                self._log(f"OAuth2 with header failed: {e}", error=True)
                raise e

    async def close(self):
        """Closes all active connections and sessions."""
        for provider_name in list(self._active_connections.keys()):
            if provider_name in self._active_connections:
                response, session = self._active_connections.pop(provider_name)
                response.close()
                await session.close()
        self._active_connections.clear()
    
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
