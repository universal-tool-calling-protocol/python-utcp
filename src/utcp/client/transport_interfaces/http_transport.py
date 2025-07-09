from typing import Dict, Any, List
import aiohttp
import json
import base64
import re

from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.shared.provider import Provider, HttpProvider
from utcp.shared.tool import Tool
from utcp.shared.utcp_manual import UtcpManual
from utcp.client.openapi_converter import OpenApiConverter
from utcp.shared.auth import ApiKeyAuth, BasicAuth, OAuth2Auth
from typing import Optional, Callable
from aiohttp import ClientSession, BasicAuth as AiohttpBasicAuth

class HttpClientTransport(ClientTransportInterface):
    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        self._session: Optional[aiohttp.ClientSession] = None
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}

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
            
            # Security check: Enforce HTTPS or localhost to prevent MITM attacks
            if not (url.startswith("https://") or url.startswith("http://localhost") or url.startswith("http://127.0.0.1")):
                raise ValueError(
                    f"Security error: URL must use HTTPS or start with 'http://localhost' or 'http://127.0.0.1'. Got: {url}. "
                    "Non-secure URLs are vulnerable to man-in-the-middle attacks."
                )
                
            self._log(f"Discovering tools from '{provider.name}' (REST) at {url}")
            
            # Use the provider's configuration (headers, auth, HTTP method, etc.)
            request_headers = provider.headers.copy() if provider.headers else {}
            body_content = None
            
            # Handle authentication
            auth = None
            if provider.auth:
                if isinstance(provider.auth, ApiKeyAuth):
                    if provider.auth.api_key:
                        request_headers[provider.auth.var_name] = provider.auth.api_key
                    else:
                        self._log("API key not found for ApiKeyAuth.", error=True)
                        raise ValueError("API key for ApiKeyAuth not found.")
                elif isinstance(provider.auth, BasicAuth):
                    auth = AiohttpBasicAuth(provider.auth.username, provider.auth.password)
                elif isinstance(provider.auth, OAuth2Auth):
                    token = await self._handle_oauth2(provider.auth)
                    request_headers["Authorization"] = f"Bearer {token}"
            
            # Handle body content if specified
            if provider.body_field:
                # For discovery, we typically don't have body content, but support it if needed
                body_content = None
            
            async with aiohttp.ClientSession() as session:
                try:
                    # Set content-type header if body is provided and header not already set
                    if body_content is not None and "Content-Type" not in request_headers:
                        request_headers["Content-Type"] = provider.content_type
                    
                    # Prepare body content based on content type
                    data = None
                    json_data = None
                    if body_content is not None:
                        if "application/json" in request_headers.get("Content-Type", ""):
                            json_data = body_content
                        else:
                            data = body_content
                    
                    # Make the request with the provider's HTTP method
                    method = provider.http_method.lower()
                    request_method = getattr(session, method)
                    
                    async with request_method(
                        url,
                        headers=request_headers,
                        auth=auth,
                        json=json_data,
                        data=data,
                        timeout=aiohttp.ClientTimeout(total=10.0)
                    ) as response:
                        response.raise_for_status()  # Raise exception for 4XX/5XX responses
                        response_data = await response.json()

                        # Check if the response is a UTCP manual or an OpenAPI spec
                        if "version" in response_data and "tools" in response_data:
                            self._log(f"Detected UTCP manual from '{provider.name}'.")
                            utcp_manual = UtcpManual(**response_data)
                        else:
                            self._log(f"Assuming OpenAPI spec from '{provider.name}'. Converting to UTCP manual.")
                            converter = OpenApiConverter(response_data, spec_url=provider.url)
                            utcp_manual = converter.convert()
                        
                        return utcp_manual.tools
                except aiohttp.ClientResponseError as e:
                    self._log(f"Error connecting to REST provider '{provider.name}': {e}", error=True)
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

        # Build the URL with path parameters substituted
        url = self._build_url_with_path_params(provider.url, remaining_args)
        
        # The rest of the arguments are query parameters
        query_params = remaining_args

        # Handle authentication
        auth = None
        if provider.auth:
            if isinstance(provider.auth, ApiKeyAuth):
                if provider.auth.api_key:
                    request_headers[provider.auth.var_name] = provider.auth.api_key
                else:
                    self._log("API key not found for ApiKeyAuth.", error=True)
                    raise ValueError("API key for ApiKeyAuth not found.")

            elif isinstance(provider.auth, BasicAuth):
                auth = AiohttpBasicAuth(provider.auth.username, provider.auth.password)

            elif isinstance(provider.auth, OAuth2Auth):
                token = await self._handle_oauth2(provider.auth)
                request_headers["Authorization"] = f"Bearer {token}"

        async with aiohttp.ClientSession() as session:
            try:
                # Set content-type header if body is provided and header not already set
                if body_content is not None and "Content-Type" not in request_headers:
                    request_headers["Content-Type"] = provider.content_type

                # Prepare body content based on content type
                data = None
                json_data = None
                if body_content is not None:
                    if "application/json" in request_headers.get("Content-Type", ""):
                        json_data = body_content
                    else:
                        data = body_content

                # Make the request with the appropriate HTTP method
                method = provider.http_method.lower()
                request_method = getattr(session, method)
                
                async with request_method(
                    url,
                    params=query_params,
                    headers=request_headers,
                    auth=auth,
                    json=json_data,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=30.0)
                ) as response:
                    response.raise_for_status()
                    return await response.json()
                    
            except aiohttp.ClientResponseError as e:
                self._log(f"Error calling tool '{tool_name}' on provider '{provider.name}': {e}", error=True)
                raise
            except Exception as e:
                self._log(f"Unexpected error calling tool '{tool_name}': {e}", error=True)
                raise

    async def _handle_oauth2(self, auth_details: OAuth2Auth) -> str:
        """Handles OAuth2 client credentials flow, trying both body and auth header methods."""
        client_id = auth_details.client_id

        if client_id in self._oauth_tokens:
            return self._oauth_tokens[client_id]["access_token"]

        async with aiohttp.ClientSession() as session:
            # Method 1: Send credentials in the request body
            try:
                self._log("Attempting OAuth2 token fetch with credentials in body.")
                body_data = {
                    'grant_type': 'client_credentials',
                    'client_id': auth_details.client_id,
                    'client_secret': auth_details.client_secret,
                    'scope': auth_details.scope
                }
                async with session.post(auth_details.token_url, data=body_data) as response:
                    response.raise_for_status()
                    token_response = await response.json()
                    self._oauth_tokens[client_id] = token_response
                    return token_response["access_token"]
            except aiohttp.ClientError as e:
                self._log(f"OAuth2 with credentials in body failed: {e}. Trying Basic Auth header.")

            # Method 2: Send credentials as Basic Auth header
            try:
                self._log("Attempting OAuth2 token fetch with Basic Auth header.")
                header_auth = AiohttpBasicAuth(auth_details.client_id, auth_details.client_secret)
                header_data = {
                    'grant_type': 'client_credentials',
                    'scope': auth_details.scope
                }
                async with session.post(auth_details.token_url, data=header_data, auth=header_auth) as response:
                    response.raise_for_status()
                    token_response = await response.json()
                    self._oauth_tokens[client_id] = token_response
                    return token_response["access_token"]
            except aiohttp.ClientError as e:
                self._log(f"OAuth2 with Basic Auth header also failed: {e}", error=True)
    
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
