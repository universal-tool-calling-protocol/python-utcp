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
    
    def __init__(self, logger: Optional[Callable[[str, Any], None]] = None):
        self._log = logger or (lambda msg, error=False: None)
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}
        self._connections: Dict[str, ClientWebSocketResponse] = {}
        self._sessions: Dict[str, ClientSession] = {}

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
            # Send discovery request
            discovery_request = {
                "type": "discover",
                "request_id": f"discover_{manual_provider.name}"
            }
            await ws.send_str(json.dumps(discovery_request))
            self._log(f"Sent discovery request to {manual_provider.url}")
            
            # Wait for discovery response
            timeout = 30  # 30 second timeout for discovery
            try:
                async with asyncio.timeout(timeout):
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                response = json.loads(msg.data)
                                if (response.get("type") == "discovery_response" and 
                                    response.get("request_id") == discovery_request["request_id"]):
                                    
                                    # Parse tools from response
                                    tools = []
                                    for tool_data in response.get("tools", []):
                                        # Create individual provider for each tool
                                        # This allows tools to have different endpoints, auth, etc.
                                        tool_provider = WebSocketProvider(
                                            name=f"{manual_provider.name}_{tool_data['name']}",
                                            url=tool_data.get("url", manual_provider.url),
                                            protocol=tool_data.get("protocol", manual_provider.protocol),
                                            keep_alive=tool_data.get("keep_alive", manual_provider.keep_alive),
                                            auth=tool_data.get("auth", manual_provider.auth),
                                            headers=tool_data.get("headers", manual_provider.headers),
                                            header_fields=tool_data.get("header_fields", manual_provider.header_fields),
                                            message_format=tool_data.get("message_format", manual_provider.message_format)
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
                                    
                                    self._log(f"Discovered {len(tools)} tools from {manual_provider.url}")
                                    return tools
                                    
                            except json.JSONDecodeError:
                                self._log(f"Invalid JSON in discovery response: {msg.data}", error=True)
                                
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            self._log(f"WebSocket error during discovery: {ws.exception()}", error=True)
                            break
                            
            except asyncio.TimeoutError:
                self._log(f"Discovery timeout for {manual_provider.url}", error=True)
                raise ValueError(f"Tool discovery timeout for WebSocket provider {manual_provider.url}")
                
        except Exception as e:
            self._log(f"Error during tool discovery: {e}", error=True)
            raise
        
        return []

    async def deregister_tool_provider(self, manual_provider: Provider) -> None:
        """Deregister a WebSocket provider by closing its connection."""
        if not isinstance(manual_provider, WebSocketProvider):
            return
        
        provider_key = f"{manual_provider.name}_{manual_provider.url}"
        await self._cleanup_connection(provider_key)
        self._log(f"Deregistered WebSocket provider {manual_provider.name}")

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
        
        ws = await self._get_connection(tool_provider)
        
        # Prepare tool call request - allow for custom format via tool_provider config
        request_id = f"call_{tool_name}_{id(arguments)}"
        
        # Check if tool_provider specifies a custom message format
        if tool_provider.message_format:
            # Allow tools to define their own message format
            # This supports existing WebSocket services without modification
            try:
                formatted_message = tool_provider.message_format.format(
                    tool_name=tool_name,
                    arguments=json.dumps(arguments),
                    request_id=request_id
                )
                call_request = json.loads(formatted_message)
            except (KeyError, json.JSONDecodeError) as e:
                self._log(f"Error formatting custom message: {e}", error=True)
                # Fall back to default format
                call_request = {
                    "type": "call_tool",
                    "request_id": request_id,
                    "tool_name": tool_name,
                    "arguments": arguments
                }
        else:
            # Default UTCP format
            call_request = {
                "type": "call_tool",
                "request_id": request_id,
                "tool_name": tool_name,
                "arguments": arguments
            }
        
        # Add any header fields to the request
        if tool_provider.header_fields and arguments:
            headers = {}
            for field in tool_provider.header_fields:
                if field in arguments:
                    headers[field] = arguments[field]
            if headers:
                call_request["headers"] = headers
        
        try:
            await ws.send_str(json.dumps(call_request))
            self._log(f"Sent tool call request for {tool_name}")
            
            # Wait for response
            timeout = 60  # 60 second timeout for tool calls
            try:
                async with asyncio.timeout(timeout):
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                response = json.loads(msg.data)
                                if response.get("request_id") == request_id:
                                    if response.get("type") == "tool_response":
                                        self._log(f"Received successful response for {tool_name}")
                                        return response.get("result")
                                    elif response.get("type") == "tool_error":
                                        error_msg = response.get("error", "Unknown error")
                                        self._log(f"Tool error for {tool_name}: {error_msg}", error=True)
                                        raise RuntimeError(f"Tool {tool_name} failed: {error_msg}")
                                        
                            except json.JSONDecodeError:
                                self._log(f"Invalid JSON in tool response: {msg.data}", error=True)
                                
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            self._log(f"WebSocket error during tool call: {ws.exception()}", error=True)
                            break
                            
            except asyncio.TimeoutError:
                self._log(f"Tool call timeout for {tool_name}", error=True)
                raise RuntimeError(f"Tool call timeout for {tool_name}")
                
        except Exception as e:
            self._log(f"Error calling tool {tool_name}: {e}", error=True)
            raise
        
        raise RuntimeError(f"No response received for tool {tool_name}")

    async def close(self) -> None:
        """Close all WebSocket connections and sessions."""
        # Close all connections
        for provider_key in list(self._connections.keys()):
            await self._cleanup_connection(provider_key)
        
        # Clear OAuth tokens
        self._oauth_tokens.clear()
        
        self._log("WebSocket transport closed")

    def __del__(self):
        """Ensure cleanup on object destruction."""
        if self._connections or self._sessions:
            # Log warning but can't await in __del__
            logging.warning("WebSocketClientTransport was not properly closed. Call close() explicitly.")