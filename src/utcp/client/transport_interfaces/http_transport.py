from typing import Dict, Any, List
import httpx
import json

from utcp.client.ClientTransportInterface import ClientTransportInterface
from utcp.shared.provider import Provider, HttpProvider
from utcp.shared.tool import Tool
from utcp.shared.utcp_response import UtcpResponse
from utcp.shared.auth import ApiKeyAuth, BasicAuth, OAuth2Auth
from typing import Optional, Callable
from authlib.integrations.httpx_client import AsyncOAuth2Client

class HttpClientTransport(ClientTransportInterface):
    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        self._oauth_clients: Dict[str, AsyncOAuth2Client] = {}

        self._log = logger or (lambda *args, **kwargs: None)

    async def register_tool_provider(self, provider: Provider) -> List[Tool]:
        """Discover tools from a REST API provider.
        
        Args:
            provider: Details of the REST provider
            
        Returns:
            List of tool declarations as dictionaries, or None if discovery fails
        """
        if not isinstance(provider, HttpProvider):
            raise ValueError("HttpTransport can only be used with HttpProvider")

        try:
            url = provider.url
            self._log(f"Discovering tools from '{provider.name}' (REST) at {url}")
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(url, timeout=10.0)
                    response.raise_for_status()  # Raise exception for 4XX/5XX responses
                    utcp_response = UtcpResponse(**response.json())
                    return utcp_response.tools
                except httpx.HTTPStatusError as e:
                    self._log(f"Error connecting to REST provider '{provider.name}': {e}", error=True)
                    if hasattr(e, 'response') and e.response is not None:
                        self._log(f"Response status: {e.response.status_code}, content: {e.response.text[:200]}", error=True)
                    return []
                except json.JSONDecodeError as e:
                    self._log(f"Error parsing JSON from REST provider '{provider.name}': {e}", error=True)
                    return []
        except Exception as e:
            self._log(f"Unexpected error discovering tools from REST provider '{provider.name}': {e}", error=True)
            return []

    async def deregister_tool_provider(self, provider: Provider) -> None:
        """Deregistering a tool provider is a no-op for the stateless HTTP transport."""
        pass

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], provider: Provider) -> Any:
        """Calls a tool on an HTTP provider."""
        if not isinstance(provider, HttpProvider):
            raise ValueError("HttpClientTransport can only be used with HttpProvider")

        request_headers = provider.headers.copy() if provider.headers else {}
        body_content = None
        
        remaining_args = arguments.copy()

        # Handle header fields
        if provider.header_fields:
            for field_name in provider.header_fields:
                if field_name in remaining_args:
                    request_headers[field_name] = str(remaining_args.pop(field_name))

        # Handle body field
        if provider.body_field and provider.body_field in remaining_args:
            body_content = remaining_args.pop(provider.body_field)

        # The rest of the arguments are query parameters
        query_params = remaining_args
        
        # Handle authentication
        auth_handler = None
        if provider.auth:
            if isinstance(provider.auth, ApiKeyAuth):
                if provider.auth.api_key:
                    request_headers[provider.auth.var_name] = provider.auth.api_key
                else:
                    self._log("API key not found for ApiKeyAuth.", error=True)
                    raise ValueError("API key for ApiKeyAuth not found.")

            elif isinstance(provider.auth, BasicAuth):
                auth_handler = httpx.BasicAuth(provider.auth.username, provider.auth.password)

            elif isinstance(provider.auth, OAuth2Auth):
                token = await self._handle_oauth2(provider.auth)
                request_headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient() as client:
            try:
                request_kwargs = {
                    "method": provider.http_method,
                    "url": provider.url,
                    "params": query_params,
                    "headers": request_headers,
                    "timeout": 30.0,
                }
                
                if auth_handler:
                    request_kwargs["auth"] = auth_handler

                if body_content is not None:
                    # Set content-type header if not already set
                    if "Content-Type" not in request_headers:
                        request_headers["Content-Type"] = provider.content_type

                    if "application/json" in request_headers.get("Content-Type", ""):
                        request_kwargs["json"] = body_content
                    else:
                        request_kwargs["data"] = body_content

                response = await client.request(**request_kwargs)
                
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                self._log(f"Error calling tool '{tool_name}' on provider '{provider.name}': {e}", error=True)
                if hasattr(e, 'response') and e.response is not None:
                    self._log(f"Response status: {e.response.status_code}, content: {e.response.text[:200]}", error=True)
                raise
            except Exception as e:
                self._log(f"Unexpected error calling tool '{tool_name}': {e}", error=True)
                raise

    async def _handle_oauth2(self, auth_details: OAuth2Auth) -> str:
        """Handles OAuth2 client credentials flow to obtain an access token."""
        client_id = auth_details.client_id

        # Reuse client if already created for this client_id
        if client_id not in self._oauth_clients:
            self._oauth_clients[client_id] = AsyncOAuth2Client(
                client_id=client_id,
                client_secret=auth_details.client_secret,
                scope=auth_details.scope,
            )
        
        client = self._oauth_clients[client_id]

        try:
            token_data = await client.fetch_token(url=auth_details.token_url)
            return token_data["access_token"]
        except Exception as e:
            self._log(f"Failed to fetch OAuth2 token: {e}", error=True)
            raise
