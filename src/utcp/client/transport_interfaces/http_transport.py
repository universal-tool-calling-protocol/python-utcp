from typing import Dict, Any, List
import aiohttp
import json
import yaml
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
    
    def _apply_auth(self, provider: HttpProvider, headers: Dict[str, str], query_params: Dict[str, Any]) -> tuple:
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
        """Discover tools from a REST API provider.

        Args:
            provider: Details of the REST provider

        Returns:
            List of tool declarations as dictionaries, or None if discovery fails
        """
        if not isinstance(manual_provider, HttpProvider):
            raise ValueError("HttpTransport can only be used with HttpProvider")

        try:
            url = manual_provider.url
            
            # Security check: Enforce HTTPS or localhost to prevent MITM attacks
            if not (url.startswith("https://") or url.startswith("http://localhost") or url.startswith("http://127.0.0.1")):
                raise ValueError(
                    f"Security error: URL must use HTTPS or start with 'http://localhost' or 'http://127.0.0.1'. Got: {url}. "
                    "Non-secure URLs are vulnerable to man-in-the-middle attacks."
                )
                
            self._log(f"Discovering tools from '{manual_provider.name}' (REST) at {url}")
            
            # Use the provider's configuration (headers, auth, HTTP method, etc.)
            request_headers = manual_provider.headers.copy() if manual_provider.headers else {}
            body_content = None
            query_params = {}
            
            # Handle authentication
            auth, cookies = self._apply_auth(manual_provider, request_headers, query_params)
            
            # Handle OAuth2 separately since it requires async token retrieval
            if manual_provider.auth and isinstance(manual_provider.auth, OAuth2Auth):
                token = await self._handle_oauth2(manual_provider.auth)
                request_headers["Authorization"] = f"Bearer {token}"
            
            # Handle body content if specified
            if manual_provider.body_field:
                # For discovery, we typically don't have body content, but support it if needed
                body_content = None
            
            async with aiohttp.ClientSession() as session:
                try:
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
                        params=query_params,
                        headers=request_headers,
                        auth=auth,
                        json=json_data,
                        data=data,
                        cookies=cookies,
                        timeout=aiohttp.ClientTimeout(total=10.0)
                    ) as response:
                        response.raise_for_status()  # Raise exception for 4XX/5XX responses

                        # Check content type to determine how to parse the response
                        content_type = response.headers.get('Content-Type', '')
                        response_text = await response.text()

                        if 'yaml' in content_type or url.endswith(('.yaml', '.yml')):
                            response_data = yaml.safe_load(response_text)
                        else:
                            response_data = json.loads(response_text)

                        # Check if the response is a UTCP manual or an OpenAPI spec
                        if "version" in response_data and "tools" in response_data:
                            self._log(f"Detected UTCP manual from '{manual_provider.name}'.")
                            utcp_manual = UtcpManual(**response_data)
                        else:
                            self._log(f"Assuming OpenAPI spec from '{manual_provider.name}'. Converting to UTCP manual.")
                            converter = OpenApiConverter(response_data, spec_url=manual_provider.url, provider_name=manual_provider.name)
                            utcp_manual = converter.convert()
                        
                        return utcp_manual.tools
                except aiohttp.ClientResponseError as e:
                    self._log(f"Error connecting to REST provider '{manual_provider.name}': {e}", error=True)
                    return []
                except (json.JSONDecodeError, yaml.YAMLError) as e:
                    self._log(f"Error parsing spec from REST provider '{manual_provider.name}': {e}", error=True)
                    return []
        except Exception as e:
            self._log(f"Unexpected error discovering tools from REST provider '{manual_provider.name}': {e}", error=True)
            return []

    async def deregister_tool_provider(self, manual_provider: Provider) -> None:
        """Deregistering a tool provider is a no-op for the stateless HTTP transport."""
        pass

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], tool_provider: Provider) -> Any:
        """Calls a tool on an HTTP provider."""
        if not isinstance(tool_provider, HttpProvider):
            raise ValueError("HttpClientTransport can only be used with HttpProvider")

        request_headers = tool_provider.headers.copy() if tool_provider.headers else {}
        body_content = None
        remaining_args = arguments.copy()

        # Handle header fields
        if tool_provider.header_fields:
            for field_name in tool_provider.header_fields:
                if field_name in remaining_args:
                    request_headers[field_name] = str(remaining_args.pop(field_name))

        # Handle body field
        if tool_provider.body_field and tool_provider.body_field in remaining_args:
            body_content = remaining_args.pop(tool_provider.body_field)

        # Build the URL with path parameters substituted
        url = self._build_url_with_path_params(tool_provider.url, remaining_args)
        
        # The rest of the arguments are query parameters
        query_params = remaining_args

        # Handle authentication
        auth, cookies = self._apply_auth(tool_provider, request_headers, query_params)
        
        # Handle OAuth2 separately since it requires async token retrieval
        if tool_provider.auth and isinstance(tool_provider.auth, OAuth2Auth):
            token = await self._handle_oauth2(tool_provider.auth)
            request_headers["Authorization"] = f"Bearer {token}"

        async with aiohttp.ClientSession() as session:
            try:
                # Set content-type header if body is provided and header not already set
                if body_content is not None and "Content-Type" not in request_headers:
                    request_headers["Content-Type"] = tool_provider.content_type

                # Prepare body content based on content type
                data = None
                json_data = None
                if body_content is not None:
                    if "application/json" in request_headers.get("Content-Type", ""):
                        json_data = body_content
                    else:
                        data = body_content

                # Make the request with the appropriate HTTP method
                method = tool_provider.http_method.lower()
                request_method = getattr(session, method)
                
                async with request_method(
                    url,
                    params=query_params,
                    headers=request_headers,
                    auth=auth,
                    json=json_data,
                    data=data,
                    cookies=cookies,
                    timeout=aiohttp.ClientTimeout(total=30.0)
                ) as response:
                    response.raise_for_status()
                    return await response.json()
                    
            except aiohttp.ClientResponseError as e:
                self._log(f"Error calling tool '{tool_name}' on provider '{tool_provider.name}': {e}", error=True)
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
