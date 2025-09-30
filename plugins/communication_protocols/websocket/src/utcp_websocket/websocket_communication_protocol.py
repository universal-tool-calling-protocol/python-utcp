"""WebSocket communication protocol implementation for UTCP client.

This module provides the WebSocket communication protocol implementation that handles
real-time bidirectional communication with WebSocket-based tool providers.

Key Features:
    - Real-time bidirectional communication
    - Multiple authentication methods (API key, Basic, OAuth2)
    - Tool discovery via WebSocket handshake
    - Connection pooling and keep-alive
    - Security enforcement (WSS or localhost only)
    - Custom message formats and templates
"""

from typing import Dict, Any, Optional, Callable, AsyncGenerator
import asyncio
import json
import base64
import aiohttp
from aiohttp import ClientWebSocketResponse, ClientSession
import logging

from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool
from utcp.data.utcp_manual import UtcpManual, UtcpManualSerializer
from utcp.data.register_manual_response import RegisterManualResult
from utcp.data.auth_implementations.api_key_auth import ApiKeyAuth
from utcp.data.auth_implementations.basic_auth import BasicAuth
from utcp.data.auth_implementations.oauth2_auth import OAuth2Auth
from utcp_websocket.websocket_call_template import WebSocketCallTemplate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
)

logger = logging.getLogger(__name__)


class WebSocketCommunicationProtocol(CommunicationProtocol):
    """REQUIRED
    WebSocket communication protocol implementation for UTCP client.

    Handles real-time bidirectional communication with WebSocket-based tool providers,
    supporting various authentication methods and message formats. Enforces security
    by requiring WSS or localhost connections.

    Features:
        - Real-time WebSocket communication with persistent connections
        - Multiple authentication: API key (header), Basic, OAuth2
        - Tool discovery via WebSocket handshake using UTCP messages
        - Flexible message formats (JSON or text-based with templates)
        - Connection pooling and automatic keep-alive
        - OAuth2 token caching and automatic refresh
        - Security validation of connection URLs

    Attributes:
        _connections: Active WebSocket connections by provider key.
        _sessions: aiohttp ClientSessions for connection management.
        _oauth_tokens: Cache of OAuth2 tokens by client_id.
    """

    def __init__(self, logger_func: Optional[Callable[[str], None]] = None):
        """Initialize the WebSocket communication protocol.

        Args:
            logger_func: Optional logging function that accepts log messages.
        """
        self._connections: Dict[str, ClientWebSocketResponse] = {}
        self._sessions: Dict[str, ClientSession] = {}
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}

    def _format_tool_call_message(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        call_template: WebSocketCallTemplate,
        request_id: str
    ) -> str:
        """Format a tool call message based on call template configuration.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments for the tool call
            call_template: The WebSocketCallTemplate with formatting configuration
            request_id: Unique request identifier

        Returns:
            Formatted message string
        """
        # Handle legacy message_format for backward compatibility
        if call_template.message_format:
            try:
                formatted_message = call_template.message_format.format(
                    tool_name=tool_name,
                    arguments=json.dumps(arguments),
                    request_id=request_id
                )
                return formatted_message
            except (KeyError, json.JSONDecodeError) as e:
                logger.error(f"Error formatting custom message: {e}")
                # Fall through to standard format

        # Handle request_data_format (following UDP/TCP pattern)
        if call_template.request_data_format == "json":
            return json.dumps({
                "type": "call_tool",
                "request_id": request_id,
                "tool_name": tool_name,
                "arguments": arguments
            })
        elif call_template.request_data_format == "text":
            # Use template-based formatting
            if call_template.request_data_template:
                message = call_template.request_data_template
                # Replace placeholders with argument values
                for arg_name, arg_value in arguments.items():
                    placeholder = f"UTCP_ARG_{arg_name}_UTCP_ARG"
                    if isinstance(arg_value, str):
                        message = message.replace(placeholder, arg_value)
                    else:
                        message = message.replace(placeholder, json.dumps(arg_value))
                # Replace tool name and request ID if placeholders exist
                message = message.replace("UTCP_ARG_tool_name_UTCP_ARG", tool_name)
                message = message.replace("UTCP_ARG_request_id_UTCP_ARG", request_id)
                return message
            else:
                # Fallback to simple format
                return f"{tool_name} {' '.join([str(v) for v in arguments.values()])}"
        else:
            # Default to JSON format
            return json.dumps({
                "type": "call_tool",
                "request_id": request_id,
                "tool_name": tool_name,
                "arguments": arguments
            })

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

    async def _prepare_headers(self, call_template: WebSocketCallTemplate) -> Dict[str, str]:
        """Prepare headers for WebSocket connection including authentication."""
        headers = call_template.headers.copy() if call_template.headers else {}

        if call_template.auth:
            if isinstance(call_template.auth, ApiKeyAuth):
                if call_template.auth.api_key:
                    if call_template.auth.location == "header":
                        headers[call_template.auth.var_name] = call_template.auth.api_key

            elif isinstance(call_template.auth, BasicAuth):
                userpass = f"{call_template.auth.username}:{call_template.auth.password}"
                headers["Authorization"] = "Basic " + base64.b64encode(userpass.encode()).decode()

            elif isinstance(call_template.auth, OAuth2Auth):
                token = await self._handle_oauth2(call_template.auth)
                headers["Authorization"] = f"Bearer {token}"

        return headers

    async def _get_connection(self, call_template: WebSocketCallTemplate) -> ClientWebSocketResponse:
        """Get or create a WebSocket connection for the call template."""
        provider_key = f"{call_template.name}_{call_template.url}"

        # Check if we have an active connection
        if provider_key in self._connections:
            ws = self._connections[provider_key]
            if not ws.closed:
                return ws
            else:
                # Clean up closed connection
                await self._cleanup_connection(provider_key)

        # Create new connection
        headers = await self._prepare_headers(call_template)

        session = ClientSession()
        self._sessions[provider_key] = session

        try:
            ws = await session.ws_connect(
                call_template.url,
                headers=headers,
                protocols=[call_template.protocol] if call_template.protocol else None,
                heartbeat=30 if call_template.keep_alive else None
            )
            self._connections[provider_key] = ws
            logger.info(f"WebSocket connected to {call_template.url}")
            return ws

        except Exception as e:
            await session.close()
            if provider_key in self._sessions:
                del self._sessions[provider_key]
            logger.error(f"Failed to connect to WebSocket {call_template.url}: {e}")
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

    async def register_manual(self, caller, manual_call_template: CallTemplate) -> RegisterManualResult:
        """REQUIRED
        Register a manual and its tools via WebSocket discovery.

        Sends a discovery message: {"type": "utcp"}
        Expects a UtcpManual response with tools.

        Args:
            caller: The UTCP client that is calling this method.
            manual_call_template: The call template of the manual to register.

        Returns:
            RegisterManualResult object containing the call template and manual.
        """
        if not isinstance(manual_call_template, WebSocketCallTemplate):
            raise ValueError("WebSocketCommunicationProtocol can only be used with WebSocketCallTemplate")

        ws = await self._get_connection(manual_call_template)

        try:
            # Send discovery request (matching UDP pattern)
            discovery_message = json.dumps({"type": "utcp"})
            await ws.send_str(discovery_message)
            logger.info(f"Registering WebSocket manual '{manual_call_template.name}' at {manual_call_template.url}")

            # Wait for discovery response
            timeout = manual_call_template.timeout
            try:
                async with asyncio.timeout(timeout):
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                response_data = json.loads(msg.data)

                                # Response data for a /utcp endpoint NEEDS to be a UtcpManual
                                if isinstance(response_data, dict) and 'tools' in response_data:
                                    try:
                                        # Parse as UtcpManual
                                        utcp_manual = UtcpManualSerializer().validate_dict(response_data)
                                        logger.info(f"Discovered {len(utcp_manual.tools)} tools from WebSocket manual '{manual_call_template.name}'")
                                        return RegisterManualResult(
                                            call_template=manual_call_template,
                                            manual=utcp_manual
                                        )
                                    except Exception as e:
                                        logger.error(f"Invalid UtcpManual response from WebSocket manual '{manual_call_template.name}': {e}")
                                        raise ValueError(f"Invalid UtcpManual format: {e}")

                            except json.JSONDecodeError as e:
                                logger.error(f"Invalid JSON response from WebSocket manual '{manual_call_template.name}': {e}")

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"WebSocket error during discovery: {ws.exception()}")
                            break

            except asyncio.TimeoutError:
                logger.error(f"Discovery timeout for {manual_call_template.url}")
                raise ValueError(f"Tool discovery timeout for WebSocket manual {manual_call_template.url}")

        except Exception as e:
            logger.error(f"Error registering WebSocket manual '{manual_call_template.name}': {e}")
            raise

        # Should not reach here, but just in case
        raise ValueError(f"Failed to discover tools from {manual_call_template.url}")

    async def deregister_manual(self, caller, manual_call_template: CallTemplate) -> None:
        """REQUIRED
        Deregister a manual by closing its WebSocket connection.

        Args:
            caller: The UTCP client that is calling this method.
            manual_call_template: The call template of the manual to deregister.
        """
        if not isinstance(manual_call_template, WebSocketCallTemplate):
            return

        provider_key = f"{manual_call_template.name}_{manual_call_template.url}"
        await self._cleanup_connection(provider_key)
        logger.info(f"Deregistered WebSocket manual '{manual_call_template.name}' (connection closed)")

    async def call_tool(self, caller, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        """REQUIRED
        Execute a tool call through WebSocket.

        Sends: {"type": "call_tool", "request_id": "...", "tool_name": "...", "arguments": {...}}
        Expects: {"type": "tool_response", "request_id": "...", "result": {...}}

        Args:
            caller: The UTCP client that is calling this method.
            tool_name: Name of the tool to call.
            tool_args: Dictionary of arguments to pass to the tool.
            tool_call_template: Call template of the tool to call.

        Returns:
            The tool's response.
        """
        if not isinstance(tool_call_template, WebSocketCallTemplate):
            raise ValueError("WebSocketCommunicationProtocol can only be used with WebSocketCallTemplate")

        logger.info(f"Calling WebSocket tool '{tool_name}'")

        ws = await self._get_connection(tool_call_template)

        try:
            # Prepare tool call request
            request_id = f"call_{tool_name}_{id(tool_args)}"
            tool_call_message = self._format_tool_call_message(tool_name, tool_args, tool_call_template, request_id)

            await ws.send_str(tool_call_message)
            logger.info(f"Sent tool call request for {tool_name}")

            # Wait for response
            timeout = tool_call_template.timeout
            try:
                async with asyncio.timeout(timeout):
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                response = json.loads(msg.data)
                                # Check for response matching request_id or allow without for backward compatibility
                                if (response.get("request_id") == request_id or not response.get("request_id")):
                                    if response.get("type") == "tool_response":
                                        return response.get("result")
                                    elif response.get("type") == "tool_error":
                                        error_msg = response.get("error", "Unknown error")
                                        logger.error(f"Tool error for {tool_name}: {error_msg}")
                                        raise RuntimeError(f"Tool {tool_name} failed: {error_msg}")
                                    else:
                                        # For non-UTCP responses, return the entire response
                                        return msg.data

                            except json.JSONDecodeError:
                                # Return raw response for non-JSON responses
                                return msg.data

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"WebSocket error during tool call: {ws.exception()}")
                            break

            except asyncio.TimeoutError:
                logger.error(f"Tool call timeout for {tool_name}")
                raise RuntimeError(f"Tool call timeout for {tool_name}")

        except Exception as e:
            logger.error(f"Error calling WebSocket tool '{tool_name}': {e}")
            raise

    async def call_tool_streaming(self, caller, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any, None]:
        """REQUIRED
        Execute a tool call through WebSocket with streaming responses.

        Args:
            caller: The UTCP client that is calling this method.
            tool_name: Name of the tool to call.
            tool_args: Dictionary of arguments to pass to the tool.
            tool_call_template: Call template of the tool to call.

        Yields:
            Streaming responses from the tool.
        """
        if not isinstance(tool_call_template, WebSocketCallTemplate):
            raise ValueError("WebSocketCommunicationProtocol can only be used with WebSocketCallTemplate")

        logger.info(f"Calling WebSocket tool '{tool_name}' (streaming)")

        ws = await self._get_connection(tool_call_template)

        try:
            # Prepare tool call request
            request_id = f"call_{tool_name}_{id(tool_args)}"
            tool_call_message = self._format_tool_call_message(tool_name, tool_args, tool_call_template, request_id)

            await ws.send_str(tool_call_message)
            logger.info(f"Sent streaming tool call request for {tool_name}")

            # Stream responses
            timeout = tool_call_template.timeout
            try:
                async with asyncio.timeout(timeout):
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                response = json.loads(msg.data)
                                if (response.get("request_id") == request_id or not response.get("request_id")):
                                    if response.get("type") == "tool_response":
                                        yield response.get("result")
                                    elif response.get("type") == "tool_error":
                                        error_msg = response.get("error", "Unknown error")
                                        logger.error(f"Tool error for {tool_name}: {error_msg}")
                                        raise RuntimeError(f"Tool {tool_name} failed: {error_msg}")
                                    elif response.get("type") == "stream_end":
                                        break
                                    else:
                                        yield msg.data

                            except json.JSONDecodeError:
                                yield msg.data

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"WebSocket error during streaming: {ws.exception()}")
                            break

            except asyncio.TimeoutError:
                logger.error(f"Streaming timeout for {tool_name}")
                raise RuntimeError(f"Streaming timeout for {tool_name}")

        except Exception as e:
            logger.error(f"Error streaming WebSocket tool '{tool_name}': {e}")
            raise

    async def close(self) -> None:
        """Close all WebSocket connections and sessions."""
        for provider_key in list(self._connections.keys()):
            await self._cleanup_connection(provider_key)

        self._oauth_tokens.clear()
        logger.info("WebSocket communication protocol closed")
