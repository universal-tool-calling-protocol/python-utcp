from typing import Dict, Any, List, Optional, Callable, Union
import asyncio
import json
import logging
import ssl
import aiohttp
from aiohttp import ClientWebSocketResponse, ClientSession
import base64

from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.shared.provider import Provider, WebSocketProvider
from utcp.shared.tool import Tool, ToolInputOutputSchema
from utcp.shared.utcp_manual import UtcpManual
from utcp.shared.auth import ApiKeyAuth, BasicAuth, OAuth2Auth


class WebSocketClientTransport(ClientTransportInterface):
    """
    WebSocket transport implementation for UTCP that provides real-time bidirectional communication.
    
    This transport supports:
    - Tool discovery via initial connection handshake
    - Real-time tool execution with streaming responses
    - Authentication (API Key, Basic Auth, OAuth2)
    - Automatic reconnection and keep-alive
    - Protocol subprotocols
    """
    
    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        self._log = logger or (lambda *args, **kwargs: None)
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}
        self._connections: Dict[str, ClientWebSocketResponse] = {}
        self._sessions: Dict[str, ClientSession] = {}
    
    def _log_info(self, message: str):
        """Log informational messages."""
        self._log(f"[WebSocketTransport] {message}")
        
    def _log_error(self, message: str):
        """Log error messages."""
        logging.error(f"[WebSocketTransport Error] {message}")

    def _format_tool_call_message(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        provider: WebSocketProvider,
        request_id: str
    ) -> str:
        """Format a tool call message based on provider configuration.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments for the tool call
            provider: The WebSocketProvider with formatting configuration
            request_id: Unique request identifier
            
        Returns:
            Formatted message string
        """
        # Check if provider specifies a custom message format
        if provider.message_format:
            # Custom format with placeholders (maintains backward compatibility)
            try:
                formatted_message = provider.message_format.format(
                    tool_name=tool_name,
                    arguments=json.dumps(arguments),
                    request_id=request_id
                )
                return formatted_message
            except (KeyError, json.JSONDecodeError) as e:
                self._log_error(f"Error formatting custom message: {e}")
                # Fall back to default format below
        
        # Handle request_data_format similar to UDP transport
        if provider.request_data_format == "json":
            return json.dumps({
                "type": "call_tool",
                "request_id": request_id,
                "tool_name": tool_name,
                "arguments": arguments
            })
        elif provider.request_data_format == "text":
            # Use template-based formatting
            if provider.request_data_template is not None and provider.request_data_template != "":
                message = provider.request_data_template
                # Replace placeholders with argument values
                for arg_name, arg_value in arguments.items():
                    placeholder = f"UTCP_ARG_{arg_name}_UTCP_ARG"
                    if isinstance(arg_value, str):
                        message = message.replace(placeholder, arg_value)
                    else:
                        message = message.replace(placeholder, json.dumps(arg_value))
                # Also replace tool name and request ID if placeholders exist
                message = message.replace("UTCP_ARG_tool_name_UTCP_ARG", tool_name)
                message = message.replace("UTCP_ARG_request_id_UTCP_ARG", request_id)
                return message
            else:
                # Fallback to simple format
                return f"{tool_name} {' '.join([str(v) for k, v in arguments.items()])}"
        else:
            # Default to JSON format
            return json.dumps({
                "type": "call_tool",
                "request_id": request_id,
                "tool_name": tool_name,
                "arguments": arguments
            })

    def _enforce_security(self, url: str):
        """Enforce HTTPS/WSS or localhost for security."""
        if not (url.startswith("wss://") or 
                url.startswith("ws://localhost") or 
                url.startswith("ws://127.0.0.1")):
            raise ValueError(
                f"Security error: WebSocket URL must use WSS or start with 'ws://localhost' or 'ws://127.0.0.1'. "
                f"Got: {url}. Non-secure URLs are vulnerable to man-in-the-middle attacks."
            )

    async def _handle_oauth2(self, auth: OAuth2Auth) -> str:
        """Handle OAuth2 authentication and token management."""
        client_id = auth.client_id
        if client_id in self._oauth_tokens:
            return self._oauth_tokens[client_id]["access_token"]
        
        async with aiohttp.ClientSession() as session:
            data = {
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': auth.client_secret,
                'scope': auth.scope
            }
            async with session.post(auth.token_url, data=data) as resp:
                resp.raise_for_status()
                token_response = await resp.json()
                self._oauth_tokens[client_id] = token_response
                return token_response["access_token"]

    async def _prepare_headers(self, provider: WebSocketProvider) -> Dict[str, str]:
        """Prepare headers for WebSocket connection including authentication."""
        headers = provider.headers.copy() if provider.headers else {}
        
        if provider.auth:
            if isinstance(provider.auth, ApiKeyAuth):
                if provider.auth.api_key:
                    if provider.auth.location == "header":
                        headers[provider.auth.var_name] = provider.auth.api_key
                # WebSocket doesn't support query params or cookies in the same way as HTTP
                
            elif isinstance(provider.auth, BasicAuth):
                userpass = f"{provider.auth.username}:{provider.auth.password}"
                headers["Authorization"] = "Basic " + base64.b64encode(userpass.encode()).decode()
                
            elif isinstance(provider.auth, OAuth2Auth):
                token = await self._handle_oauth2(provider.auth)
                headers["Authorization"] = f"Bearer {token}"
        
        return headers

    async def _get_connection(self, provider: WebSocketProvider) -> ClientWebSocketResponse:
        """Get or create a WebSocket connection for the provider."""
        provider_key = f"{provider.name}_{provider.url}"
        
        # Check if we have an active connection
        if provider_key in self._connections:
            ws = self._connections[provider_key]
            if not ws.closed:
                return ws
            else:
                # Clean up closed connection
                await self._cleanup_connection(provider_key)
        
        # Create new connection
        self._enforce_security(provider.url)
        headers = await self._prepare_headers(provider)
        
        session = ClientSession()
        self._sessions[provider_key] = session
        
        try:
            ws = await session.ws_connect(
                provider.url,
                headers=headers,
                protocols=[provider.protocol] if provider.protocol else None,
                heartbeat=30 if provider.keep_alive else None
            )
            self._connections[provider_key] = ws
            self._log(f"WebSocket connected to {provider.url}")
            return ws
            
        except Exception as e:
            await session.close()
            if provider_key in self._sessions:
                del self._sessions[provider_key]
            self._log(f"Failed to connect to WebSocket {provider.url}: {e}", error=True)
            raise

    async def _cleanup_connection(self, provider_key: str):
        """Clean up a specific connection."""
        if provider_key in self._connections:
            ws = self._connections[provider_key]
            if not ws.closed:
                await ws.close()
            del self._connections[provider_key]
        
        if provider_key in self._sessions:
            session = self._sessions[provider_key]
            await session.close()
            del self._sessions[provider_key]

    async def register_tool_provider(self, manual_provider: Provider) -> List[Tool]:
        """
        Register a WebSocket tool provider by connecting and requesting tool discovery.
        
        The discovery protocol sends a JSON message:
        {"type": "discover", "request_id": "unique_id"}
        
        Expected response:
        {"type": "discovery_response", "request_id": "unique_id", "tools": [...]}
        """
        if not isinstance(manual_provider, WebSocketProvider):
            raise ValueError("WebSocketClientTransport can only be used with WebSocketProvider")
        
        ws = await self._get_connection(manual_provider)
        
        try:
            # Send discovery request (matching UDP pattern)
            discovery_message = json.dumps({
                "type": "utcp"
            })
            await ws.send_str(discovery_message)
            self._log_info(f"Registering WebSocket provider '{manual_provider.name}' at {manual_provider.url}")
            
            # Wait for discovery response
            timeout = manual_provider.timeout / 1000.0  # Convert ms to seconds
            try:
                async with asyncio.timeout(timeout):
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                response_data = json.loads(msg.data)
                                
                                # Check if response contains tools (matching UDP pattern)
                                if isinstance(response_data, dict) and 'tools' in response_data:
                                    tools_data = response_data['tools']
                                    
                                    # Parse tools
                                    tools = []
                                    for tool_data in tools_data:
                                        try:
                                            # Create individual provider for each tool
                                            # This allows tools to have different endpoints, auth, etc.
                                            tool_provider = WebSocketProvider(
                                                name=f"{manual_provider.name}_{tool_data['name']}",
                                                url=tool_data.get("url", manual_provider.url),
                                                protocol=tool_data.get("protocol", manual_provider.protocol),
                                                keep_alive=tool_data.get("keep_alive", manual_provider.keep_alive),
                                                request_data_format=tool_data.get("request_data_format", manual_provider.request_data_format),
                                                request_data_template=tool_data.get("request_data_template", manual_provider.request_data_template),
                                                message_format=tool_data.get("message_format", manual_provider.message_format),
                                                timeout=tool_data.get("timeout", manual_provider.timeout),
                                                auth=tool_data.get("auth", manual_provider.auth),
                                                headers=tool_data.get("headers", manual_provider.headers),
                                                header_fields=tool_data.get("header_fields", manual_provider.header_fields)
                                            )
                                            
                                            tool = Tool(
                                                name=tool_data["name"],
                                                description=tool_data.get("description", ""),
                                                inputs=ToolInputOutputSchema(**tool_data.get("inputs", {})),
                                                outputs=ToolInputOutputSchema(**tool_data.get("outputs", {})),
                                                tags=tool_data.get("tags", []),
                                                tool_provider=tool_provider
                                            )
                                            tools.append(tool)
                                        except Exception as e:
                                            self._log_error(f"Invalid tool definition in WebSocket provider '{manual_provider.name}': {e}")
                                            continue
                                    
                                    self._log_info(f"Discovered {len(tools)} tools from WebSocket provider '{manual_provider.name}'")
                                    return tools
                                else:
                                    self._log_info(f"No tools found in WebSocket provider '{manual_provider.name}' response")
                                    return []
                                    
                            except json.JSONDecodeError as e:
                                self._log_error(f"Invalid JSON response from WebSocket provider '{manual_provider.name}': {e}")
                                
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            self._log_error(f"WebSocket error during discovery: {ws.exception()}")
                            break
                            
            except asyncio.TimeoutError:
                self._log_error(f"Discovery timeout for {manual_provider.url}")
                raise ValueError(f"Tool discovery timeout for WebSocket provider {manual_provider.url}")
                
        except Exception as e:
            self._log_error(f"Error registering WebSocket provider '{manual_provider.name}': {e}")
            return []
        
        return []

    async def deregister_tool_provider(self, manual_provider: Provider) -> None:
        """Deregister a WebSocket provider by closing its connection."""
        if not isinstance(manual_provider, WebSocketProvider):
            return
        
        provider_key = f"{manual_provider.name}_{manual_provider.url}"
        await self._cleanup_connection(provider_key)
        self._log_info(f"Deregistering WebSocket provider '{manual_provider.name}' (connection closed)")

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], tool_provider: Provider) -> Any:
        """
        Call a tool via WebSocket.
        
        The format can be customized per tool, but defaults to:
        {"type": "call_tool", "request_id": "unique_id", "tool_name": "tool", "arguments": {...}}
        
        Expected response:
        {"type": "tool_response", "request_id": "unique_id", "result": {...}}
        or
        {"type": "tool_error", "request_id": "unique_id", "error": "error message"}
        """
        if not isinstance(tool_provider, WebSocketProvider):
            raise ValueError("WebSocketClientTransport can only be used with WebSocketProvider")
        
        self._log_info(f"Calling WebSocket tool '{tool_name}' on provider '{tool_provider.name}'")
        
        ws = await self._get_connection(tool_provider)
        
        try:
            # Prepare tool call request using the new formatting method
            request_id = f"call_{tool_name}_{id(arguments)}"
            tool_call_message = self._format_tool_call_message(tool_name, arguments, tool_provider, request_id)
            
            # For JSON format, we need to parse it back to add header fields if needed
            if tool_provider.request_data_format == "json" or tool_provider.message_format:
                try:
                    call_request = json.loads(tool_call_message)
                    
                    # Add any header fields to the request
                    if tool_provider.header_fields and arguments:
                        headers = {}
                        for field in tool_provider.header_fields:
                            if field in arguments:
                                headers[field] = arguments[field]
                        if headers:
                            call_request["headers"] = headers
                    
                    tool_call_message = json.dumps(call_request)
                except json.JSONDecodeError:
                    # Keep the original message if it's not valid JSON
                    pass
            
            await ws.send_str(tool_call_message)
            self._log_info(f"Sent tool call request for {tool_name}")
            
            # Wait for response
            timeout = tool_provider.timeout / 1000.0  # Convert ms to seconds
            try:
                async with asyncio.timeout(timeout):
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                response = json.loads(msg.data)
                                # Check for either new format or backward compatible format
                                if (response.get("request_id") == request_id or 
                                    not response.get("request_id")):  # Allow responses without request_id for backward compatibility
                                    if response.get("type") == "tool_response":
                                        return response.get("result")
                                    elif response.get("type") == "tool_error":
                                        error_msg = response.get("error", "Unknown error")
                                        self._log_error(f"Tool error for {tool_name}: {error_msg}")
                                        raise RuntimeError(f"Tool {tool_name} failed: {error_msg}")
                                    else:
                                        # For non-UTCP responses, return the entire response
                                        return msg.data
                                        
                            except json.JSONDecodeError:
                                # Return raw response for non-JSON responses
                                return msg.data
                                
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            self._log_error(f"WebSocket error during tool call: {ws.exception()}")
                            break
                            
            except asyncio.TimeoutError:
                self._log_error(f"Tool call timeout for {tool_name}")
                raise RuntimeError(f"Tool call timeout for {tool_name}")
                
        except Exception as e:
            self._log_error(f"Error calling WebSocket tool '{tool_name}': {e}")
            raise

    async def close(self) -> None:
        """Close all WebSocket connections and sessions."""
        # Close all connections
        for provider_key in list(self._connections.keys()):
            await self._cleanup_connection(provider_key)
        
        # Clear OAuth tokens
        self._oauth_tokens.clear()
        
        self._log_info("WebSocket transport closed")

    def __del__(self):
        """Ensure cleanup on object destruction."""
        if self._connections or self._sessions:
            # Log warning but can't await in __del__
            logging.warning("WebSocketClientTransport was not properly closed. Call close() explicitly.")