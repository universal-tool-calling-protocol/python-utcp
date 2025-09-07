"""
Transmission Control Protocol (TCP) transport for UTCP client.

This transport communicates with tools over TCP sockets.
"""
import asyncio
import json
import socket
import struct
import sys
from typing import Dict, Any, List, Optional, Callable, Union

from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.shared.provider import Provider, TCPProvider
from utcp.shared.tool import Tool
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
)

logger = logging.getLogger(__name__)

class TCPTransport(ClientTransportInterface):
    """Transport implementation for TCP-based tool providers.
    
    This transport communicates with tools over TCP sockets. It supports:
    - Tool discovery via TCP messages
    - Tool execution by sending TCP packets with arguments
    - Multiple framing strategies: length-prefix, delimiter, fixed-length, and stream
    - JSON and text-based request formatting
    - Template-based argument substitution
    - Configurable response byte format (text encoding or raw bytes)
    - Connection management for each request
    """
    
    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        """Initialize the TCP transport.
        
        Args:
            logger: Optional logger function for debugging
        """
        self._log = logger or (lambda *args, **kwargs: None)
    
    def _log_info(self, message: str):
        """Log informational messages."""
        self._log(f"[TCPTransport] {message}")
        
    def _log_error(self, message: str):
        """Log error messages."""
        logger.error(f"[TCPTransport Error] {message}")
    
    def _format_tool_call_message(
        self,
        tool_args: Dict[str, Any],
        provider: TCPProvider
    ) -> str:
        """Format a tool call message based on provider configuration.
        
        Args:
            tool_args: Arguments for the tool call
            provider: The TCPProvider with formatting configuration
            
        Returns:
            Formatted message string
        """
        if provider.request_data_format == "json":
            return json.dumps(tool_args)
        elif provider.request_data_format == "text":
            # Use template-based formatting
            if provider.request_data_template is not None and provider.request_data_template != "":
                message = provider.request_data_template
                # Replace placeholders with argument values
                for arg_name, arg_value in tool_args.items():
                    placeholder = f"UTCP_ARG_{arg_name}_UTCP_ARG"
                    if isinstance(arg_value, str):
                        message = message.replace(placeholder, arg_value)
                    else:
                        message = message.replace(placeholder, json.dumps(arg_value))
                return message
            else:
                # Fallback to simple key=value format
                return " ".join([str(v) for k, v in tool_args.items()])
        else:
            # Default to JSON format
            return json.dumps(tool_args)
    
    def _encode_message_with_framing(self, message: str, provider: TCPProvider) -> bytes:
        """Encode message with appropriate TCP framing.
        
        Args:
            message: Message to encode
            provider: TCPProvider with framing configuration
            
        Returns:
            Framed message bytes
        """
        message_bytes = message.encode('utf-8')
        
        if provider.framing_strategy == "length_prefix":
            # Add length prefix before the message
            length = len(message_bytes)
            if provider.length_prefix_bytes == 1:
                length_bytes = struct.pack(f"{'>' if provider.length_prefix_endian == 'big' else '<'}B", length)
            elif provider.length_prefix_bytes == 2:
                length_bytes = struct.pack(f"{'>' if provider.length_prefix_endian == 'big' else '<'}H", length)
            elif provider.length_prefix_bytes == 4:
                length_bytes = struct.pack(f"{'>' if provider.length_prefix_endian == 'big' else '<'}I", length)
            elif provider.length_prefix_bytes == 8:
                length_bytes = struct.pack(f"{'>' if provider.length_prefix_endian == 'big' else '<'}Q", length)
            else:
                raise ValueError(f"Invalid length_prefix_bytes: {provider.length_prefix_bytes}")
            return length_bytes + message_bytes
        
        elif provider.framing_strategy == "delimiter":
            # Add delimiter after the message
            delimiter = provider.message_delimiter or "\\x00"
            # Handle escape sequences
            delimiter = delimiter.encode('utf-8').decode('unicode_escape')
            return message_bytes + delimiter.encode('utf-8')
        
        elif provider.framing_strategy in ("fixed_length", "stream"):
            # No additional framing needed
            return message_bytes
        
        else:
            raise ValueError(f"Unknown framing strategy: {provider.framing_strategy}")
    
    def _decode_response_with_framing(self, sock: socket.socket, provider: TCPProvider, timeout: float) -> bytes:
        """Decode response based on TCP framing strategy.
        
        Args:
            sock: Connected TCP socket
            provider: TCPProvider with framing configuration
            timeout: Read timeout in seconds
            
        Returns:
            Response message bytes
        """
        sock.settimeout(timeout)
        
        if provider.framing_strategy == "length_prefix":
            # Read length prefix first
            length_bytes = sock.recv(provider.length_prefix_bytes)
            if len(length_bytes) < provider.length_prefix_bytes:
                raise Exception(f"Incomplete length prefix: got {len(length_bytes)} bytes, expected {provider.length_prefix_bytes}")
            
            # Unpack length
            if provider.length_prefix_bytes == 1:
                length = struct.unpack(f"{'>' if provider.length_prefix_endian == 'big' else '<'}B", length_bytes)[0]
            elif provider.length_prefix_bytes == 2:
                length = struct.unpack(f"{'>' if provider.length_prefix_endian == 'big' else '<'}H", length_bytes)[0]
            elif provider.length_prefix_bytes == 4:
                length = struct.unpack(f"{'>' if provider.length_prefix_endian == 'big' else '<'}I", length_bytes)[0]
            elif provider.length_prefix_bytes == 8:
                length = struct.unpack(f"{'>' if provider.length_prefix_endian == 'big' else '<'}Q", length_bytes)[0]
            else:
                raise ValueError(f"Invalid length_prefix_bytes: {provider.length_prefix_bytes}")
            
            # Read the message data
            response_data = b""
            while len(response_data) < length:
                chunk = sock.recv(length - len(response_data))
                if not chunk:
                    raise Exception("Connection closed while reading message")
                response_data += chunk
            
            return response_data
        
        elif provider.framing_strategy == "delimiter":
            # Read until delimiter is found
            delimiter = provider.message_delimiter or "\\x00"
            delimiter = delimiter.encode('utf-8').decode('unicode_escape').encode('utf-8')
            
            response_data = b""
            while True:
                chunk = sock.recv(1)
                if not chunk:
                    raise Exception("Connection closed while reading message")
                response_data += chunk
                
                # Check if we've received the delimiter
                if response_data.endswith(delimiter):
                    # Remove delimiter from response
                    return response_data[:-len(delimiter)]
        
        elif provider.framing_strategy == "fixed_length":
            # Read exactly fixed_message_length bytes
            if provider.fixed_message_length is None:
                raise ValueError("fixed_message_length must be set for fixed_length framing")
            
            response_data = b""
            while len(response_data) < provider.fixed_message_length:
                chunk = sock.recv(provider.fixed_message_length - len(response_data))
                if not chunk:
                    raise Exception("Connection closed while reading message")
                response_data += chunk
            
            return response_data
        
        elif provider.framing_strategy == "stream":
            # Read until connection closes or max_response_size is reached
            response_data = b""
            while len(response_data) < provider.max_response_size:
                try:
                    chunk = sock.recv(min(4096, provider.max_response_size - len(response_data)))
                    if not chunk:
                        # Connection closed
                        break
                    response_data += chunk
                except socket.timeout:
                    # Timeout reached
                    break
            
            return response_data
        
        else:
            raise ValueError(f"Unknown framing strategy: {provider.framing_strategy}")

    async def _send_tcp_message(
        self,
        host: str,
        port: int,
        message: str,
        provider: TCPProvider,
        timeout: float = 30.0,
        response_encoding: Optional[str] = "utf-8"
    ) -> Union[str, bytes]:
        """Send a TCP message and wait for response.
        
        Args:
            host: Host to connect to
            port: Port to connect to
            message: Message to send
            provider: TCPProvider with framing configuration
            timeout: Timeout in seconds
            response_encoding: Encoding to decode response bytes. If None, returns raw bytes.
            
        Returns:
            Response message or raw bytes if encoding is None
        """
        loop = asyncio.get_event_loop()
        
        def _send_and_receive():
            """Blocking function to send TCP message and receive response."""
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # Set connection timeout
                sock.settimeout(timeout)
                
                # Connect to server
                sock.connect((host, port))
                
                # Encode message with framing
                framed_message = self._encode_message_with_framing(message, provider)
                
                # Send message
                sock.sendall(framed_message)
                
                # Receive response based on framing strategy
                response_bytes = self._decode_response_with_framing(sock, provider, timeout)
                
                return response_bytes
                
            except socket.timeout:
                raise Exception(f"TCP connection timeout after {timeout} seconds")
            except Exception as e:
                raise Exception(f"TCP communication error: {e}")
            finally:
                sock.close()
        
        try:
            # Run blocking socket operations in executor
            response_bytes = await loop.run_in_executor(None, _send_and_receive)
            
            # Return based on encoding preference
            if response_encoding is None:
                return response_bytes
            else:
                try:
                    return response_bytes.decode(response_encoding)
                except UnicodeDecodeError as e:
                    self._log_error(f"Failed to decode response with encoding '{response_encoding}': {e}")
                    # Return raw bytes as fallback
                    return response_bytes
                    
        except Exception as e:
            self._log_error(f"Error in TCP communication: {e}")
            raise

    async def register_tool_provider(self, manual_provider: Provider) -> List[Tool]:
        """Register a TCP provider and discover its tools.
        
        Sends a discovery message to the TCP provider and parses the response.
        
        Args:
            manual_provider: The TCPProvider to register
            
        Returns:
            List of tools discovered from the TCP provider
            
        Raises:
            ValueError: If provider is not a TCPProvider
        """
        if not isinstance(manual_provider, TCPProvider):
            raise ValueError("TCPTransport can only be used with TCPProvider")
        
        self._log_info(f"Registering TCP provider '{manual_provider.name}'")
        
        try:
            # Send discovery message
            discovery_message = json.dumps({
                "type": "utcp"
            })
            
            response = await self._send_tcp_message(
                manual_provider.host,
                manual_provider.port,
                discovery_message,
                manual_provider,
                manual_provider.timeout / 1000.0,  # Convert ms to seconds
                manual_provider.response_byte_format
            )
            
            # Parse response
            try:
                # Handle bytes response by trying to decode as UTF-8 for JSON parsing
                if isinstance(response, bytes):
                    response_str = response.decode('utf-8')
                else:
                    response_str = response
                    
                response_data = json.loads(response_str)
                
                # Check if response contains tools
                if isinstance(response_data, dict) and 'tools' in response_data:
                    tools_data = response_data['tools']
                    
                    # Parse tools
                    tools = []
                    for tool_data in tools_data:
                        try:
                            tool = Tool(**tool_data)
                            tools.append(tool)
                        except Exception as e:
                            self._log_error(f"Invalid tool definition in TCP provider '{manual_provider.name}': {e}")
                            continue
                    
                    self._log_info(f"Discovered {len(tools)} tools from TCP provider '{manual_provider.name}'")
                    return tools
                else:
                    self._log_info(f"No tools found in TCP provider '{manual_provider.name}' response")
                    return []
                    
            except json.JSONDecodeError as e:
                self._log_error(f"Invalid JSON response from TCP provider '{manual_provider.name}': {e}")
                return []
                
        except Exception as e:
            self._log_error(f"Error registering TCP provider '{manual_provider.name}': {e}")
            return []
    
    async def deregister_tool_provider(self, manual_provider: Provider) -> None:
        """Deregister a TCP provider.
        
        This is a no-op for TCP providers since connections are created per request.
        
        Args:
            manual_provider: The provider to deregister
        """
        if not isinstance(manual_provider, TCPProvider):
            raise ValueError("TCPTransport can only be used with TCPProvider")
            
        self._log_info(f"Deregistering TCP provider '{manual_provider.name}' (no-op)")
    
    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any], tool_provider: Provider) -> Any:
        """Call a TCP tool.
        
        Sends a tool call message to the TCP provider and returns the response.
        
        Args:
            tool_name: Name of the tool to call
            tool_args: Arguments for the tool call
            tool_provider: The TCPProvider containing the tool
            
        Returns:
            The response from the TCP tool
            
        Raises:
            ValueError: If provider is not a TCPProvider
        """
        if not isinstance(tool_provider, TCPProvider):
            raise ValueError("TCPTransport can only be used with TCPProvider")
        
        self._log_info(f"Calling TCP tool '{tool_name}' on provider '{tool_provider.name}'")
        
        try:
            tool_call_message = self._format_tool_call_message(tool_args, tool_provider)
            
            response = await self._send_tcp_message(
                tool_provider.host,
                tool_provider.port,
                tool_call_message,
                tool_provider,
                tool_provider.timeout / 1000.0,  # Convert ms to seconds
                tool_provider.response_byte_format
            )
            return response
                
        except Exception as e:
            self._log_error(f"Error calling TCP tool '{tool_name}': {e}")
            raise
