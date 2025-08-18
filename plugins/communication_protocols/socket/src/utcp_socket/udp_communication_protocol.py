"""
User Datagram Protocol (UDP) transport for UTCP client.

This transport communicates with tools over UDP sockets.
"""
import asyncio
import json
import logging
import socket
import traceback
from typing import Dict, Any, List, Optional, Callable, Union

from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.shared.provider import Provider, UDPProvider
from utcp.shared.tool import Tool


class UDPTransport(ClientTransportInterface):
    """Transport implementation for UDP-based tool providers.
    
    This transport communicates with tools over UDP sockets. It supports:
    - Tool discovery via UDP messages
    - Tool execution by sending UDP packets with arguments
    - Multiple response datagrams handling
    - JSON and text-based request formatting
    - Template-based argument substitution
    - Configurable response byte format (text encoding or raw bytes)
    - Stateless operation (no persistent connections)
    """
    
    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        """Initialize the UDP transport.
        
        Args:
            logger: Optional logger function for debugging
        """
        self._log = logger or (lambda *args, **kwargs: None)
        # UDP is stateless, so no connections to manage
    
    def _log_info(self, message: str):
        """Log informational messages."""
        self._log(f"[UDPTransport] {message}")
        
    def _log_error(self, message: str):
        """Log error messages."""
        logging.error(f"[UDPTransport Error] {message}")
    
    def _format_tool_call_message(
        self,
        tool_args: Dict[str, Any],
        provider: UDPProvider
    ) -> str:
        """Format a tool call message based on provider configuration.
        
        Args:
            tool_args: Arguments for the tool call
            provider: The UDPProvider with formatting configuration
            
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
    
    async def _send_udp_message(
        self,
        host: str,
        port: int,
        message: str,
        timeout: float = 30.0,
        num_response_datagrams: int = 1,
        response_encoding: Optional[str] = "utf-8"
    ) -> Union[str, bytes]:
        """Send a UDP message and wait for response(s).
        
        Args:
            host: Host to send message to
            port: Port to send message to
            message: Message to send
            timeout: Timeout in seconds
            num_response_datagrams: Number of response datagrams to receive
            response_encoding: Encoding to decode response bytes. If None, returns raw bytes.
            
        Returns:
            Response message (concatenated if multiple datagrams) or raw bytes if encoding is None
        """
        if num_response_datagrams == 0:
            # No response expected - just send and return
            await self._send_udp_no_response(host, port, message)
            return b"" if response_encoding is None else ""
        
        # Use simple socket approach with executor for Windows compatibility
        loop = asyncio.get_event_loop()
        
        def _send_and_receive():
            """Blocking function to send UDP message and receive responses."""
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # Resolve host to IP for comparison
                try:
                    resolved_host_ip = socket.gethostbyname(host)
                except socket.gaierror:
                    resolved_host_ip = host  # Fallback to original if resolution fails
                
                # Send message
                message_bytes = message.encode('utf-8')
                sock.sendto(message_bytes, (host, port))
                
                # Collect responses
                response_bytes_list = []
                
                for i in range(max(1, num_response_datagrams)):
                    try:
                        # Use shorter timeout for subsequent datagrams
                        current_timeout = timeout if i == 0 else 1.0
                        
                        # Set socket timeout
                        sock.settimeout(current_timeout)
                        
                        # Receive response
                        data, addr = sock.recvfrom(65535)
                        
                        # Verify it's from the expected host (compare with resolved IP)
                        if addr[0] == host or addr[0] == resolved_host_ip:
                            response_bytes_list.append(data)
                        else:
                            # Got response from wrong host, don't count it
                            continue
                            
                    except socket.timeout:
                        if i == 0:
                            # First datagram timed out
                            raise TimeoutError(f"UDP request timed out after {timeout} seconds")
                        else:
                            # Subsequent datagrams timed out, but we have some data
                            break
                
                return response_bytes_list
                
            finally:
                sock.close()
        
        try:
            # Run blocking socket operations in executor
            response_bytes_list = await loop.run_in_executor(None, _send_and_receive)
            
            # Concatenate response bytes
            combined_bytes = b''.join(response_bytes_list)
            
            # Return based on encoding preference
            if response_encoding is None:
                return combined_bytes
            else:
                try:
                    return combined_bytes.decode(response_encoding)
                except UnicodeDecodeError as e:
                    self._log_error(f"Failed to decode response with encoding '{response_encoding}': {e}")
                    # Return raw bytes as fallback
                    return combined_bytes
                    
        except TimeoutError as e:
            self._log_error(traceback.format_exc())
            raise asyncio.TimeoutError(traceback.format_exc())
        except Exception as e:
            self._log_error(f"Error sending UDP message: {traceback.format_exc()}")
            raise
    
    async def _send_udp_no_response(self, host: str, port: int, message: str) -> None:
        """Send a UDP message without expecting a response."""
        def _send_only():
            """Blocking function to send UDP message only."""
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                message_bytes = message.encode('utf-8')
                sock.sendto(message_bytes, (host, port))
            finally:
                sock.close()
        
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _send_only)
        except Exception as e:
            self._log_error(f"Error sending UDP message (no response): {traceback.format_exc()}")
            raise
    
    async def register_tool_provider(self, manual_provider: Provider) -> List[Tool]:
        """Register a UDP provider and discover its tools.
        
        Sends a discovery message to the UDP provider and parses the response.
        
        Args:
            manual_provider: The UDPProvider to register
            
        Returns:
            List of tools discovered from the UDP provider
            
        Raises:
            ValueError: If provider is not a UDPProvider
        """
        if not isinstance(manual_provider, UDPProvider):
            raise ValueError("UDPTransport can only be used with UDPProvider")
        
        self._log_info(f"Registering UDP provider '{manual_provider.name}' at {manual_provider.host}:{manual_provider.port}")
        
        try:
            # Send discovery message
            discovery_message = json.dumps({
                "type": "utcp"
            })
            
            response = await self._send_udp_message(
                manual_provider.host,
                manual_provider.port,
                discovery_message,
                manual_provider.timeout / 1000.0,  # Convert ms to seconds
                manual_provider.number_of_response_datagrams,
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
                            self._log_error(f"Invalid tool definition in UDP provider '{manual_provider.name}': {traceback.format_exc()}")
                            continue
                    
                    self._log_info(f"Discovered {len(tools)} tools from UDP provider '{manual_provider.name}'")
                    return tools
                else:
                    self._log_info(f"No tools found in UDP provider '{manual_provider.name}' response")
                    return []
                    
            except json.JSONDecodeError as e:
                self._log_error(f"Invalid JSON response from UDP provider '{manual_provider.name}': {traceback.format_exc()}")
                return []
                
        except Exception as e:
            self._log_error(f"Error registering UDP provider '{manual_provider.name}': {traceback.format_exc()}")
            return []
    
    async def deregister_tool_provider(self, manual_provider: Provider) -> None:
        """Deregister a UDP provider.
        
        This is a no-op for UDP providers since they are stateless.
        
        Args:
            manual_provider: The provider to deregister
        """
        if not isinstance(manual_provider, UDPProvider):
            raise ValueError("UDPTransport can only be used with UDPProvider")
            
        self._log_info(f"Deregistering UDP provider '{manual_provider.name}' (no-op)")
    
    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any], tool_provider: Provider) -> Any:
        """Call a UDP tool.
        
        Sends a tool call message to the UDP provider and returns the response.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments for the tool call
            tool_provider: The UDPProvider containing the tool
            
        Returns:
            The response from the UDP tool
            
        Raises:
            ValueError: If provider is not a UDPProvider
        """
        if not isinstance(tool_provider, UDPProvider):
            raise ValueError("UDPTransport can only be used with UDPProvider")
        
        self._log_info(f"Calling UDP tool '{tool_name}' on provider '{tool_provider.name}'")
        
        try:
            tool_call_message = self._format_tool_call_message(tool_args, tool_provider)
            
            response = await self._send_udp_message(
                tool_provider.host,
                tool_provider.port,
                tool_call_message,
                tool_provider.timeout / 1000.0,  # Convert ms to seconds
                tool_provider.number_of_response_datagrams,
                tool_provider.response_byte_format
            )
            return response
                
        except Exception as e:
            self._log_error(f"Error calling UDP tool '{tool_name}': {traceback.format_exc()}")
            raise
