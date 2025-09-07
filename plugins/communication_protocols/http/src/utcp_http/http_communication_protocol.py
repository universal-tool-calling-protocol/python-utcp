"""HTTP communication protocol implementation for UTCP client.

This module provides the HTTP communication protocol implementation that handles communication
with HTTP-based tool providers. It supports RESTful APIs, authentication methods,
URL path parameters, and automatic tool discovery through various formats.

Key Features:
    - Multiple authentication methods (API key, Basic, OAuth2)
    - URL path parameter substitution
    - Automatic tool discovery from UTCP manuals, OpenAPI specs, and YAML
    - Security enforcement (HTTPS or localhost only)
    - Request/response handling with proper error management
"""

import sys
from typing import Dict, Any, List, Optional, Callable, AsyncGenerator
import aiohttp
import json
import yaml
import base64
import re
import traceback
from urllib.parse import quote

from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool
from utcp.data.utcp_manual import UtcpManual, UtcpManualSerializer
from utcp.data.register_manual_response import RegisterManualResult
from utcp.data.auth_implementations.api_key_auth import ApiKeyAuth
from utcp.data.auth_implementations.basic_auth import BasicAuth
from utcp.data.auth_implementations.oauth2_auth import OAuth2Auth
from utcp_http.http_call_template import HttpCallTemplate
from aiohttp import ClientSession, BasicAuth as AiohttpBasicAuth
from utcp_http.openapi_converter import OpenApiConverter
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
)

logger = logging.getLogger(__name__)

class HttpCommunicationProtocol(CommunicationProtocol):
    """REQUIRED
    HTTP communication protocol implementation for UTCP client.

    Handles communication with HTTP-based tool providers, supporting various
    authentication methods, URL path parameters, and automatic tool discovery.
    Enforces security by requiring HTTPS or localhost connections.

    Features:
        - RESTful API communication with configurable HTTP methods
        - Multiple authentication: API key (header/query/cookie), Basic, OAuth2
        - URL path parameter substitution from tool arguments
        - Tool discovery from UTCP manuals, OpenAPI specs, and YAML
        - Request body and header field mapping from tool arguments
        - OAuth2 token caching and automatic refresh
        - Security validation of connection URLs

    Attributes:
        _session: Optional aiohttp ClientSession for connection reuse.
        _oauth_tokens: Cache of OAuth2 tokens by client_id.
        _log: Logger function for debugging and error reporting.
    """

    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        """Initialize the HTTP transport.

        Args:
            logger: Optional logging function that accepts log messages.
                Defaults to a no-op function if not provided.
        """
        self._session: Optional[aiohttp.ClientSession] = None
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}
    
    def _apply_auth(self, provider: HttpCallTemplate, headers: Dict[str, str], query_params: Dict[str, Any]) -> tuple:
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

    async def register_manual(self, caller, manual_call_template: CallTemplate) -> RegisterManualResult:
        """REQUIRED
        Register a manual and its tools.

        Args:
            caller: The UTCP client that is calling this method.
            manual_call_template: The call template of the manual to register.

        Returns:
            RegisterManualResult object containing the call template and manual.
        """
        if not isinstance(manual_call_template, HttpCallTemplate):
            raise ValueError("HttpCommunicationProtocol can only be used with HttpCallTemplate")

        try:
            url = manual_call_template.url
            
            # Security check: Enforce HTTPS or localhost to prevent MITM attacks
            if not (url.startswith("https://") or url.startswith("http://localhost") or url.startswith("http://127.0.0.1")):
                raise ValueError(
                    f"Security error: URL must use HTTPS or start with 'http://localhost' or 'http://127.0.0.1'. Got: {url}. "
                    "Non-secure URLs are vulnerable to man-in-the-middle attacks."
                )
                
            logger.info(f"Discovering tools from '{manual_call_template.name}' (HTTP) at {url}")
            
            # Use the call template's configuration (headers, auth, HTTP method, etc.)
            request_headers = manual_call_template.headers.copy() if manual_call_template.headers else {}
            body_content = None
            query_params = {}
            
            # Handle authentication
            auth, cookies = self._apply_auth(manual_call_template, request_headers, query_params)
            
            # Handle OAuth2 separately since it requires async token retrieval
            if manual_call_template.auth and isinstance(manual_call_template.auth, OAuth2Auth):
                token = await self._handle_oauth2(manual_call_template.auth)
                request_headers["Authorization"] = f"Bearer {token}"
            
            # Handle body content if specified
            if manual_call_template.body_field:
                # For discovery, we typically don't have body content, but support it if needed
                body_content = None
            
            async with aiohttp.ClientSession() as session:
                try:
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
                    
                    # Make the request with the call template's HTTP method
                    method = manual_call_template.http_method.lower()
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
                        if "utcp_version" in response_data and "tools" in response_data:
                            logger.info(f"Detected UTCP manual from '{manual_call_template.name}'.")
                            utcp_manual = UtcpManualSerializer().validate_dict(response_data)
                        else:
                            logger.info(f"Assuming OpenAPI spec from '{manual_call_template.name}'. Converting to UTCP manual.")
                            converter = OpenApiConverter(response_data, spec_url=manual_call_template.url, call_template_name=manual_call_template.name)
                            utcp_manual = converter.convert()
                        
                        return RegisterManualResult(
                            success=True,
                            manual_call_template=manual_call_template,
                            manual=utcp_manual,
                            errors=[]
                        )
                except aiohttp.ClientResponseError as e:
                    error_msg = f"Error connecting to HTTP provider '{manual_call_template.name}': {e}"
                    logger.error(error_msg)
                    return RegisterManualResult(
                        success=False,
                        manual_call_template=manual_call_template,
                        manual=UtcpManual(manual_version="0.0.0", tools=[]),
                        errors=[error_msg]
                    )
                except (json.JSONDecodeError, yaml.YAMLError) as e:
                    error_msg = f"Error parsing spec from HTTP provider '{manual_call_template.name}': {e}"
                    logger.error(error_msg)
                    return RegisterManualResult(
                        success=False,
                        manual_call_template=manual_call_template,
                        manual=UtcpManual(manual_version="0.0.0", tools=[]),
                        errors=[error_msg]
                    )
        except Exception as e:
            error_msg = f"Unexpected error discovering tools from HTTP provider '{manual_call_template.name}': {traceback.format_exc()}"
            logger.error(error_msg)
            return RegisterManualResult(
                success=False,
                manual_call_template=manual_call_template,
                manual=UtcpManual(manual_version="0.0.0", tools=[]),
                errors=[error_msg]
            )

    async def deregister_manual(self, caller, manual_call_template: CallTemplate) -> None:
        """REQUIRED
        Deregister a manual and its tools.
        
        Deregistering a manual is a no-op for the stateless HTTP communication protocol.
        """
        pass

    async def call_tool(self, caller, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        """REQUIRED
        Execute a tool call through this transport.
        
        Args:
            caller: The UTCP client that is calling this method.
            tool_name: Name of the tool to call (may include provider prefix).
            tool_args: Dictionary of arguments to pass to the tool.
            tool_call_template: Call template of the tool to call.
            
        Returns:
            The tool's response, with type depending on the tool's output schema.
        """
        if not isinstance(tool_call_template, HttpCallTemplate):
            raise ValueError("HttpCommunicationProtocol can only be used with HttpCallTemplate")

        request_headers = tool_call_template.headers.copy() if tool_call_template.headers else {}
        body_content = None
        remaining_args = tool_args.copy()

        # Handle header fields
        if tool_call_template.header_fields:
            for field_name in tool_call_template.header_fields:
                if field_name in remaining_args:
                    request_headers[field_name] = str(remaining_args.pop(field_name))

        # Handle body field
        if tool_call_template.body_field and tool_call_template.body_field in remaining_args:
            body_content = remaining_args.pop(tool_call_template.body_field)

        # Build the URL with path parameters substituted
        url = self._build_url_with_path_params(tool_call_template.url, remaining_args)
        
        # The rest of the arguments are query parameters
        query_params = remaining_args

        # Handle authentication
        auth, cookies = self._apply_auth(tool_call_template, request_headers, query_params)
        
        # Handle OAuth2 separately since it requires async token retrieval
        if tool_call_template.auth and isinstance(tool_call_template.auth, OAuth2Auth):
            token = await self._handle_oauth2(tool_call_template.auth)
            request_headers["Authorization"] = f"Bearer {token}"

        async with aiohttp.ClientSession() as session:
            try:
                # Set content-type header if body is provided and header not already set
                if body_content is not None and "Content-Type" not in request_headers:
                    request_headers["Content-Type"] = tool_call_template.content_type

                # Prepare body content based on content type
                data = None
                json_data = None
                if body_content is not None:
                    if "application/json" in request_headers.get("Content-Type", ""):
                        json_data = body_content
                    else:
                        data = body_content

                # Make the request with the appropriate HTTP method
                method = tool_call_template.http_method.lower()
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
                    
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'application/json' in content_type:
                        try:
                            return await response.json()
                        except Exception:
                            logger.error(f"Error parsing JSON response from tool '{tool_name}' on call template '{tool_call_template.name}', even though Content-Type was application/json")
                            return await response.text()
                    return await response.text()
                    
            except aiohttp.ClientResponseError as e:
                logger.error(f"Error calling tool '{tool_name}' on call template '{tool_call_template.name}': {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error calling tool '{tool_name}': {e}")
                raise

    async def call_tool_streaming(self, caller, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any, None]:
        """REQUIRED
        Execute a tool call through this transport streamingly.
        
        Args:
            caller: The UTCP client that is calling this method.
            tool_name: Name of the tool to call (may include provider prefix).
            tool_args: Dictionary of arguments to pass to the tool.
            tool_call_template: Call template of the tool to call.
            
        Returns:
            An async generator that yields the tool's response.
        """
        # For HTTP, streaming is not typically supported, so we'll just yield the complete response
        result = await self.call_tool(caller, tool_name, tool_args, tool_call_template)
        yield result

    async def _handle_oauth2(self, auth_details: OAuth2Auth) -> str:
        """
        Handles OAuth2 client credentials flow, trying both body and auth header methods."""
        client_id = auth_details.client_id

        if client_id in self._oauth_tokens:
            return self._oauth_tokens[client_id]["access_token"]

        async with aiohttp.ClientSession() as session:
            # Method 1: Send credentials in the request body
            try:
                logger.info("Attempting OAuth2 token fetch with credentials in body.")
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
                logger.error(f"OAuth2 with credentials in body failed: {e}. Trying Basic Auth header.")

            # Method 2: Send credentials as Basic Auth header
            try:
                logger.info("Attempting OAuth2 token fetch with Basic Auth header.")
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
                logger.error(f"OAuth2 with Basic Auth header also failed: {e}")
    
    def _build_url_with_path_params(self, url_template: str, tool_args: Dict[str, Any]) -> str:
        """
        Build URL by substituting path parameters from arguments.
        
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
