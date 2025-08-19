# import pytest
# import pytest_asyncio
# import json
# import asyncio
# import socket
# import struct
# import threading
# from unittest.mock import MagicMock, patch, AsyncMock

# from utcp.client.transport_interfaces.tcp_transport import TCPTransport
# from utcp.shared.provider import TCPProvider
# from utcp.shared.tool import Tool, ToolInputOutputSchema


# class MockTCPServer:
#     """Mock TCP server for testing."""
    
#     def __init__(self, host='localhost', port=0, response_delay=0.0):
#         self.host = host
#         self.port = port
#         self.sock = None
#         self.running = False
#         self.responses = {}  # Map message -> response
#         self.call_count = 0
#         self.server_task = None
#         self.connections = []
#         self.response_delay = response_delay  # Delay before sending response (seconds)
        
#     async def start(self):
#         """Start the mock TCP server."""
#         # Create socket and bind
#         self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#         self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#         self.sock.bind((self.host, self.port))
#         if self.port == 0:  # Auto-assign port
#             self.port = self.sock.getsockname()[1]
        
#         self.sock.listen(5)
#         self.running = True
        
#         # Start listening task
#         self.server_task = asyncio.create_task(self._accept_connections())
        
#         # Give the server a moment to start
#         await asyncio.sleep(0.1)
        
#     async def stop(self):
#         """Stop the mock TCP server."""
#         self.running = False
#         if self.server_task:
#             self.server_task.cancel()
#             try:
#                 await self.server_task
#             except asyncio.CancelledError:
#                 pass
        
#         # Close all active connections
#         for conn in self.connections:
#             try:
#                 conn.close()
#             except Exception:
#                 pass
#         self.connections.clear()
        
#         if self.sock:
#             self.sock.close()
            
#     async def _accept_connections(self):
#         """Accept incoming TCP connections."""
#         self.sock.setblocking(False)
        
#         while self.running:
#             try:
#                 conn, addr = await asyncio.get_event_loop().sock_accept(self.sock)
#                 self.connections.append(conn)
#                 # Handle each connection in a separate task
#                 asyncio.create_task(self._handle_connection(conn, addr))
#             except asyncio.CancelledError:
#                 break
#             except Exception as e:
#                 if self.running:
#                     print(f"Mock TCP server accept error: {e}")
#                 await asyncio.sleep(0.01)
                
#     async def _handle_connection(self, conn, addr):
#         """Handle a single TCP connection."""
#         try:
#             # Read data from client
#             data = await asyncio.get_event_loop().sock_recv(conn, 4096)
#             if not data:
#                 return
            
#             self.call_count += 1
            
#             try:
#                 message = data.decode('utf-8')
#             except UnicodeDecodeError:
#                 message = data.hex()  # Fallback for binary data
                
#             # Get response for this message
#             response = self.responses.get(message, '{"error": "unknown_message"}')
            
#             # Convert response to bytes
#             if isinstance(response, str):
#                 response_bytes = response.encode('utf-8')
#             elif isinstance(response, bytes):
#                 response_bytes = response
#             elif isinstance(response, dict) or isinstance(response, list):
#                 response_bytes = json.dumps(response).encode('utf-8')
#             else:
#                 response_bytes = str(response).encode('utf-8')
            
#             # Add delay if configured
#             if self.response_delay > 0:
#                 await asyncio.sleep(self.response_delay)
            
#             # Send response back
#             await asyncio.get_event_loop().sock_sendall(conn, response_bytes)
            
#         except Exception as e:
#             if self.running:
#                 print(f"Mock TCP server connection error: {e}")
#         finally:
#             try:
#                 conn.close()
#             except Exception:
#                 pass
#             if conn in self.connections:
#                 self.connections.remove(conn)
                
#     def set_response(self, message, response):
#         """Set a response for a specific message."""
#         self.responses[message] = response


# class MockTCPServerWithFraming(MockTCPServer):
#     """Mock TCP server that handles different framing strategies."""
    
#     def __init__(self, host='localhost', port=0, framing_strategy='stream', response_delay=0.0):
#         super().__init__(host, port, response_delay)
#         self.framing_strategy = framing_strategy
#         self.length_prefix_bytes = 4
#         self.length_prefix_endian = 'big'
#         self.message_delimiter = '\n'
#         self.fixed_message_length = None
        
#     async def _handle_connection(self, conn, addr):
#         """Handle a single TCP connection with framing."""
#         try:
#             if self.framing_strategy == 'length_prefix':
#                 # Read length prefix first
#                 length_data = await asyncio.get_event_loop().sock_recv(conn, self.length_prefix_bytes)
#                 if not length_data:
#                     return
                
#                 if self.length_prefix_bytes == 1:
#                     message_length = struct.unpack(f"{'>' if self.length_prefix_endian == 'big' else '<'}B", length_data)[0]
#                 elif self.length_prefix_bytes == 2:
#                     message_length = struct.unpack(f"{'>' if self.length_prefix_endian == 'big' else '<'}H", length_data)[0]
#                 elif self.length_prefix_bytes == 4:
#                     message_length = struct.unpack(f"{'>' if self.length_prefix_endian == 'big' else '<'}I", length_data)[0]
                
#                 # Read the actual message
#                 data = await asyncio.get_event_loop().sock_recv(conn, message_length)
                
#             elif self.framing_strategy == 'delimiter':
#                 # Read until delimiter
#                 data = b''
#                 delimiter_bytes = self.message_delimiter.encode('utf-8')
#                 while not data.endswith(delimiter_bytes):
#                     chunk = await asyncio.get_event_loop().sock_recv(conn, 1)
#                     if not chunk:
#                         break
#                     data += chunk
#                 # Remove delimiter
#                 data = data[:-len(delimiter_bytes)]
                
#             elif self.framing_strategy == 'fixed_length':
#                 # Read fixed number of bytes
#                 data = await asyncio.get_event_loop().sock_recv(conn, self.fixed_message_length)
                
#             else:  # stream
#                 # Read all available data
#                 data = await asyncio.get_event_loop().sock_recv(conn, 4096)
            
#             if not data:
#                 return
                
#             self.call_count += 1
            
#             try:
#                 message = data.decode('utf-8')
#             except UnicodeDecodeError:
#                 message = data.hex()
                
#             # Get response for this message
#             response = self.responses.get(message, '{"error": "unknown_message"}')
            
#             # Convert response to bytes
#             if isinstance(response, str):
#                 response_bytes = response.encode('utf-8')
#             elif isinstance(response, bytes):
#                 response_bytes = response
#             elif isinstance(response, dict) or isinstance(response, list):
#                 response_bytes = json.dumps(response).encode('utf-8')
#             else:
#                 response_bytes = str(response).encode('utf-8')
            
#             # Add delay if configured
#             if self.response_delay > 0:
#                 await asyncio.sleep(self.response_delay)
            
#             # Send response with appropriate framing
#             if self.framing_strategy == 'length_prefix':
#                 # Add length prefix
#                 length = len(response_bytes)
#                 if self.length_prefix_bytes == 1:
#                     length_bytes = struct.pack(f"{'>' if self.length_prefix_endian == 'big' else '<'}B", length)
#                 elif self.length_prefix_bytes == 2:
#                     length_bytes = struct.pack(f"{'>' if self.length_prefix_endian == 'big' else '<'}H", length)
#                 elif self.length_prefix_bytes == 4:
#                     length_bytes = struct.pack(f"{'>' if self.length_prefix_endian == 'big' else '<'}I", length)
                
#                 await asyncio.get_event_loop().sock_sendall(conn, length_bytes + response_bytes)
                
#             elif self.framing_strategy == 'delimiter':
#                 # Add delimiter
#                 delimiter_bytes = self.message_delimiter.encode('utf-8')
#                 await asyncio.get_event_loop().sock_sendall(conn, response_bytes + delimiter_bytes)
                
#             else:  # stream or fixed_length
#                 await asyncio.get_event_loop().sock_sendall(conn, response_bytes)
            
#         except Exception as e:
#             if self.running:
#                 print(f"Mock TCP server connection error: {e}")
#         finally:
#             try:
#                 conn.close()
#             except Exception:
#                 pass
#             if conn in self.connections:
#                 self.connections.remove(conn)


# @pytest_asyncio.fixture
# async def mock_tcp_server():
#     """Create a mock TCP server for testing."""
#     server = MockTCPServer()
#     await server.start()
#     yield server
#     await server.stop()


# @pytest_asyncio.fixture
# async def mock_tcp_server_length_prefix():
#     """Create a mock TCP server with length-prefix framing."""
#     server = MockTCPServerWithFraming(framing_strategy='length_prefix')
#     await server.start()
#     yield server
#     await server.stop()


# @pytest_asyncio.fixture
# async def mock_tcp_server_delimiter():
#     """Create a mock TCP server with delimiter framing."""
#     server = MockTCPServerWithFraming(framing_strategy='delimiter')
#     await server.start()
#     yield server
#     await server.stop()


# @pytest_asyncio.fixture
# async def mock_tcp_server_slow():
#     """Create a mock TCP server with a 2-second response delay."""
#     server = MockTCPServer(response_delay=2.0)  # 2-second delay
#     await server.start()
#     yield server
#     await server.stop()


# @pytest.fixture
# def logger():
#     """Create a mock logger."""
#     return MagicMock()


# @pytest.fixture
# def tcp_transport(logger):
#     """Create a TCP transport instance."""
#     return TCPTransport(logger=logger)


# @pytest.fixture
# def tcp_provider(mock_tcp_server):
#     """Create a basic TCP provider for testing."""
#     return TCPProvider(
#         name="test_tcp_provider",
#         host=mock_tcp_server.host,
#         port=mock_tcp_server.port,
#         request_data_format="json",
#         response_byte_format="utf-8",
#         framing_strategy="stream",
#         timeout=5000
#     )


# @pytest.fixture
# def text_template_provider(mock_tcp_server):
#     """Create a TCP provider with text template format."""
#     return TCPProvider(
#         name="text_template_provider",
#         host=mock_tcp_server.host,
#         port=mock_tcp_server.port,
#         request_data_format="text",
#         request_data_template="ACTION UTCP_ARG_cmd_UTCP_ARG PARAM UTCP_ARG_value_UTCP_ARG",
#         response_byte_format="utf-8",
#         framing_strategy="stream",
#         timeout=5000
#     )


# @pytest.fixture
# def raw_bytes_provider(mock_tcp_server):
#     """Create a TCP provider that returns raw bytes."""
#     return TCPProvider(
#         name="raw_bytes_provider",
#         host=mock_tcp_server.host,
#         port=mock_tcp_server.port,
#         request_data_format="json",
#         response_byte_format=None,  # Raw bytes
#         framing_strategy="stream",
#         timeout=5000
#     )


# @pytest.fixture
# def length_prefix_provider(mock_tcp_server_length_prefix):
#     """Create a TCP provider with length-prefix framing."""
#     return TCPProvider(
#         name="length_prefix_provider",
#         host=mock_tcp_server_length_prefix.host,
#         port=mock_tcp_server_length_prefix.port,
#         request_data_format="json",
#         response_byte_format="utf-8",
#         framing_strategy="length_prefix",
#         length_prefix_bytes=4,
#         length_prefix_endian="big",
#         timeout=5000
#     )


# @pytest.fixture
# def delimiter_provider(mock_tcp_server_delimiter):
#     """Create a TCP provider with delimiter framing."""
#     return TCPProvider(
#         name="delimiter_provider",
#         host=mock_tcp_server_delimiter.host,
#         port=mock_tcp_server_delimiter.port,
#         request_data_format="json",
#         response_byte_format="utf-8",
#         framing_strategy="delimiter",
#         message_delimiter="\n",
#         timeout=5000
#     )


# # Test register_tool_provider
# @pytest.mark.asyncio
# async def test_register_tool_provider(tcp_transport, tcp_provider, mock_tcp_server, logger):
#     """Test registering a tool provider."""
#     # Set up discovery response
#     discovery_response = {
#         "tools": [
#             {
#                 "name": "test_tool",
#                 "description": "A test tool",
#                 "inputs": {
#                     "type": "object",
#                     "properties": {
#                         "param1": {"type": "string", "description": "First parameter"}
#                     },
#                     "required": ["param1"]
#                 },
#                 "outputs": {
#                     "type": "object",
#                     "properties": {
#                         "result": {"type": "string", "description": "Result"}
#                     }
#                 },
#                 "tool_provider": tcp_provider.model_dump()
#             }
#         ]
#     }
    
#     mock_tcp_server.set_response('{"type": "utcp"}', discovery_response)
    
#     # Register the provider
#     tools = await tcp_transport.register_tool_provider(tcp_provider)
    
#     # Check results
#     assert len(tools) == 1
#     assert tools[0].name == "test_tool"
#     assert tools[0].description == "A test tool"
#     assert mock_tcp_server.call_count == 1
    
#     # Verify logger was called
#     logger.assert_called()


# @pytest.mark.asyncio
# async def test_register_tool_provider_empty_response(tcp_transport, tcp_provider, mock_tcp_server):
#     """Test registering a tool provider with empty response."""
#     mock_tcp_server.set_response('{"type": "utcp"}', {"tools": []})
    
#     tools = await tcp_transport.register_tool_provider(tcp_provider)
    
#     assert len(tools) == 0
#     assert mock_tcp_server.call_count == 1


# @pytest.mark.asyncio
# async def test_register_tool_provider_invalid_json(tcp_transport, tcp_provider, mock_tcp_server):
#     """Test registering a tool provider with invalid JSON response."""
#     mock_tcp_server.set_response('{"type": "utcp"}', "invalid json response")
    
#     tools = await tcp_transport.register_tool_provider(tcp_provider)
    
#     assert len(tools) == 0


# @pytest.mark.asyncio
# async def test_register_tool_provider_invalid_provider_type(tcp_transport):
#     """Test registering a non-TCP provider raises ValueError."""
#     from utcp.shared.provider import HttpProvider
    
#     invalid_provider = HttpProvider(url="http://example.com")
    
#     with pytest.raises(ValueError, match="TCPTransport can only be used with TCPProvider"):
#         await tcp_transport.register_tool_provider(invalid_provider)


# # Test deregister_tool_provider
# @pytest.mark.asyncio
# async def test_deregister_tool_provider(tcp_transport, tcp_provider):
#     """Test deregistering a tool provider (should be a no-op)."""
#     # Should not raise any exceptions
#     await tcp_transport.deregister_tool_provider(tcp_provider)


# @pytest.mark.asyncio
# async def test_deregister_tool_provider_invalid_type(tcp_transport):
#     """Test deregistering a non-TCP provider raises ValueError."""
#     from utcp.shared.provider import HttpProvider
    
#     invalid_provider = HttpProvider(url="http://example.com")
    
#     with pytest.raises(ValueError, match="TCPTransport can only be used with TCPProvider"):
#         await tcp_transport.deregister_tool_provider(invalid_provider)


# # Test call_tool with JSON format
# @pytest.mark.asyncio
# async def test_call_tool_json_format(tcp_transport, tcp_provider, mock_tcp_server):
#     """Test calling a tool with JSON format."""
#     mock_tcp_server.set_response('{"param1": "value1"}', '{"result": "success"}')
    
#     arguments = {"param1": "value1"}
#     result = await tcp_transport.call_tool("test_tool", arguments, tcp_provider)
    
#     assert result == '{"result": "success"}'
#     assert mock_tcp_server.call_count == 1


# @pytest.mark.asyncio
# async def test_call_tool_text_template_format(tcp_transport, text_template_provider, mock_tcp_server):
#     """Test calling a tool with text template format."""
#     mock_tcp_server.set_response("ACTION get PARAM data123", '{"result": "template_success"}')
    
#     arguments = {"cmd": "get", "value": "data123"}
#     result = await tcp_transport.call_tool("test_tool", arguments, text_template_provider)
    
#     assert result == '{"result": "template_success"}'
#     assert mock_tcp_server.call_count == 1


# @pytest.mark.asyncio
# async def test_call_tool_text_format_no_template(tcp_transport, mock_tcp_server):
#     """Test calling a tool with text format but no template."""
#     provider = TCPProvider(
#         name="no_template_provider",
#         host=mock_tcp_server.host,
#         port=mock_tcp_server.port,
#         request_data_format="text",
#         request_data_template=None,
#         response_byte_format="utf-8",
#         framing_strategy="stream",
#         timeout=5000
#     )
    
#     # Should use fallback format (space-separated values)
#     mock_tcp_server.set_response("value1 value2", '{"result": "fallback_success"}')
    
#     arguments = {"param1": "value1", "param2": "value2"}
#     result = await tcp_transport.call_tool("test_tool", arguments, provider)
    
#     assert result == '{"result": "fallback_success"}'


# @pytest.mark.asyncio
# async def test_call_tool_raw_bytes_response(tcp_transport, raw_bytes_provider, mock_tcp_server):
#     """Test calling a tool that returns raw bytes."""
#     binary_response = b'\x01\x02\x03\x04'
#     mock_tcp_server.set_response('{"param1": "value1"}', binary_response)
    
#     arguments = {"param1": "value1"}
#     result = await tcp_transport.call_tool("test_tool", arguments, raw_bytes_provider)
    
#     assert result == binary_response
#     assert isinstance(result, bytes)


# @pytest.mark.asyncio
# async def test_call_tool_invalid_provider_type(tcp_transport):
#     """Test calling a tool with non-TCP provider raises ValueError."""
#     from utcp.shared.provider import HttpProvider
    
#     invalid_provider = HttpProvider(url="http://example.com")
    
#     with pytest.raises(ValueError, match="TCPTransport can only be used with TCPProvider"):
#         await tcp_transport.call_tool("test_tool", {}, invalid_provider)


# # Test framing strategies
# @pytest.mark.asyncio
# async def test_call_tool_length_prefix_framing(tcp_transport, length_prefix_provider, mock_tcp_server_length_prefix):
#     """Test calling a tool with length-prefix framing."""
#     mock_tcp_server_length_prefix.set_response('{"param1": "value1"}', '{"result": "length_prefix_success"}')
    
#     arguments = {"param1": "value1"}
#     result = await tcp_transport.call_tool("test_tool", arguments, length_prefix_provider)
    
#     assert result == '{"result": "length_prefix_success"}'


# @pytest.mark.asyncio
# async def test_call_tool_delimiter_framing(tcp_transport, delimiter_provider, mock_tcp_server_delimiter):
#     """Test calling a tool with delimiter framing."""
#     mock_tcp_server_delimiter.set_response('{"param1": "value1"}', '{"result": "delimiter_success"}')
    
#     arguments = {"param1": "value1"}
#     result = await tcp_transport.call_tool("test_tool", arguments, delimiter_provider)
    
#     assert result == '{"result": "delimiter_success"}'


# @pytest.mark.asyncio
# async def test_call_tool_fixed_length_framing(tcp_transport, mock_tcp_server):
#     """Test calling a tool with fixed-length framing."""
#     provider = TCPProvider(
#         name="fixed_length_provider",
#         host=mock_tcp_server.host,
#         port=mock_tcp_server.port,
#         request_data_format="json",
#         response_byte_format="utf-8",
#         framing_strategy="fixed_length",
#         fixed_message_length=20,
#         timeout=5000
#     )
    
#     # Set up server to handle fixed-length messages
#     mock_tcp_server.responses['{"param1": "value1"}'] = '{"result": "fixed"}'.ljust(20)  # Pad to 20 bytes
    
#     arguments = {"param1": "value1"}
#     result = await tcp_transport.call_tool("test_tool", arguments, provider)
    
#     assert '{"result": "fixed"}' in result


# # Test message formatting
# def test_format_tool_call_message_json(tcp_transport):
#     """Test formatting tool call message with JSON format."""
#     provider = TCPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         request_data_format="json"
#     )
    
#     arguments = {"param1": "value1", "param2": 123}
#     result = tcp_transport._format_tool_call_message(arguments, provider)
    
#     assert result == json.dumps(arguments)


# def test_format_tool_call_message_text_with_template(tcp_transport):
#     """Test formatting tool call message with text template."""
#     provider = TCPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         request_data_format="text",
#         request_data_template="ACTION UTCP_ARG_cmd_UTCP_ARG PARAM UTCP_ARG_value_UTCP_ARG"
#     )
    
#     arguments = {"cmd": "get", "value": "data123"}
#     result = tcp_transport._format_tool_call_message(arguments, provider)
    
#     # Should substitute placeholders
#     assert result == "ACTION get PARAM data123"


# def test_format_tool_call_message_text_with_complex_values(tcp_transport):
#     """Test formatting tool call message with complex values in template."""
#     provider = TCPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         request_data_format="text",
#         request_data_template="DATA UTCP_ARG_obj_UTCP_ARG"
#     )
    
#     arguments = {"obj": {"nested": "value", "number": 123}}
#     result = tcp_transport._format_tool_call_message(arguments, provider)
    
#     # Should JSON-serialize complex values
#     assert result == 'DATA {"nested": "value", "number": 123}'


# def test_format_tool_call_message_text_no_template(tcp_transport):
#     """Test formatting tool call message with text format but no template."""
#     provider = TCPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         request_data_format="text",
#         request_data_template=None
#     )
    
#     arguments = {"param1": "value1", "param2": "value2"}
#     result = tcp_transport._format_tool_call_message(arguments, provider)
    
#     # Should use fallback format (space-separated values)
#     assert result == "value1 value2"


# def test_format_tool_call_message_default_to_json(tcp_transport):
#     """Test formatting tool call message defaults to JSON for unknown format."""
#     # Create a provider with valid format first
#     provider = TCPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         request_data_format="json"
#     )
    
#     # Manually set an invalid format to test the fallback behavior
#     provider.request_data_format = "unknown"  # Invalid format
    
#     arguments = {"param1": "value1"}
#     result = tcp_transport._format_tool_call_message(arguments, provider)
    
#     # Should default to JSON
#     assert result == json.dumps(arguments)


# # Test framing encoding and decoding
# def test_encode_message_with_length_prefix_framing(tcp_transport):
#     """Test encoding message with length-prefix framing."""
#     provider = TCPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         framing_strategy="length_prefix",
#         length_prefix_bytes=4,
#         length_prefix_endian="big"
#     )
    
#     message = "test message"
#     result = tcp_transport._encode_message_with_framing(message, provider)
    
#     # Should have 4-byte big-endian length prefix
#     expected_length = len(message.encode('utf-8'))
#     expected_prefix = struct.pack('>I', expected_length)
    
#     assert result.startswith(expected_prefix)
#     assert result[4:] == message.encode('utf-8')


# def test_encode_message_with_delimiter_framing(tcp_transport):
#     """Test encoding message with delimiter framing."""
#     provider = TCPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         framing_strategy="delimiter",
#         message_delimiter="\n"
#     )
    
#     message = "test message"
#     result = tcp_transport._encode_message_with_framing(message, provider)
    
#     # Should have delimiter appended
#     assert result == (message + "\n").encode('utf-8')


# def test_encode_message_with_stream_framing(tcp_transport):
#     """Test encoding message with stream framing."""
#     provider = TCPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         framing_strategy="stream"
#     )
    
#     message = "test message"
#     result = tcp_transport._encode_message_with_framing(message, provider)
    
#     # Should just be the raw message
#     assert result == message.encode('utf-8')


# # Test error handling and edge cases
# @pytest.mark.asyncio
# async def test_call_tool_server_error(tcp_transport, tcp_provider, mock_tcp_server):
#     """Test handling server errors during tool calls."""
#     # Don't set any response, so the server will return an error
#     arguments = {"param1": "value1"}
    
#     # Call the tool - should get the default error response
#     result = await tcp_transport.call_tool("test_tool", arguments, tcp_provider)
    
#     # Should receive the default error message
#     assert '{"error": "unknown_message"}' in result


# @pytest.mark.asyncio
# async def test_register_tool_provider_malformed_tool(tcp_transport, tcp_provider, mock_tcp_server):
#     """Test registering provider with malformed tool definition."""
#     # Set up discovery response with invalid tool
#     discovery_response = {
#         "tools": [
#             {
#                 "name": "test_tool",
#                 # Missing required fields like inputs, outputs, tool_provider
#             }
#         ]
#     }
    
#     mock_tcp_server.set_response('{"type": "utcp"}', discovery_response)
    
#     # Register the provider - should handle invalid tool gracefully
#     tools = await tcp_transport.register_tool_provider(tcp_provider)
    
#     # Should return empty list due to invalid tool definition
#     assert len(tools) == 0


# @pytest.mark.asyncio
# async def test_register_tool_provider_bytes_response(tcp_transport, tcp_provider, mock_tcp_server):
#     """Test registering provider that returns bytes response."""
#     # Set up discovery response as JSON but provider returns raw bytes
#     discovery_response = '{"tools": []}'.encode('utf-8')
    
#     mock_tcp_server.set_response('{"type": "utcp"}', discovery_response)
    
#     # Register the provider - should handle bytes response by decoding
#     tools = await tcp_transport.register_tool_provider(tcp_provider)
    
#     # Should successfully decode and parse
#     assert len(tools) == 0


# # Test logging functionality
# @pytest.mark.asyncio
# async def test_logging_calls(tcp_transport, tcp_provider, mock_tcp_server, logger):
#     """Test that logging functions are called appropriately."""
#     # Set up discovery response
#     discovery_response = {"tools": []}
#     mock_tcp_server.set_response('{"type": "utcp"}', discovery_response)
    
#     # Register provider
#     await tcp_transport.register_tool_provider(tcp_provider)
    
#     # Verify logger was called
#     logger.assert_called()
    
#     # Call tool
#     mock_tcp_server.set_response('{}', {"result": "test"})
#     await tcp_transport.call_tool("test_tool", {}, tcp_provider)
    
#     # Logger should have been called multiple times
#     assert logger.call_count > 1


# # Test timeout handling
# @pytest.mark.asyncio
# async def test_call_tool_timeout(tcp_transport):
#     """Test calling a tool with timeout using delimiter framing."""
#     # Create a slow server with delimiter framing
#     slow_server = MockTCPServerWithFraming(
#         framing_strategy='delimiter',
#         response_delay=2.0  # 2-second delay
#     )
#     await slow_server.start()
    
#     try:
#         # Create provider with 1-second timeout, but server has 2-second delay
#         provider = TCPProvider(
#             name="timeout_provider",
#             host=slow_server.host,
#             port=slow_server.port,
#             request_data_format="json",
#             response_byte_format="utf-8",
#             framing_strategy="delimiter",
#             message_delimiter="\n",
#             timeout=1000  # 1 second timeout, but server delays 2 seconds
#         )
        
#         # Set up a response (server will delay 2 seconds before responding)
#         slow_server.set_response('{"param1": "value1"}', '{"result": "delayed_response"}')
        
#         arguments = {"param1": "value1"}
        
#         # Should timeout because server takes 2 seconds but timeout is 1 second
#         # Delimiter framing will treat timeout as an error since it expects a complete message
#         with pytest.raises(Exception):  # Expect timeout error
#             await tcp_transport.call_tool("test_tool", arguments, provider)
#     finally:
#         await slow_server.stop()


# @pytest.mark.asyncio
# async def test_call_tool_connection_refused(tcp_transport):
#     """Test calling a tool when connection is refused."""
#     # Use a port that's definitely not listening
#     provider = TCPProvider(
#         name="refused_provider",
#         host="localhost",
#         port=1,  # Port 1 should be refused
#         request_data_format="json",
#         response_byte_format="utf-8",
#         framing_strategy="stream",
#         timeout=5000
#     )
    
#     arguments = {"param1": "value1"}
    
#     # Should handle connection error gracefully
#     with pytest.raises(Exception):  # Expect connection refused or similar
#         await tcp_transport.call_tool("test_tool", arguments, provider)


# # Test different byte encodings
# @pytest.mark.asyncio
# async def test_call_tool_different_encodings(tcp_transport, mock_tcp_server):
#     """Test calling a tool with different response byte encodings."""
#     # Test ASCII encoding
#     provider_ascii = TCPProvider(
#         name="ascii_provider",
#         host=mock_tcp_server.host,
#         port=mock_tcp_server.port,
#         request_data_format="json",
#         response_byte_format="ascii",
#         framing_strategy="stream",
#         timeout=5000
#     )
    
#     mock_tcp_server.set_response('{"param1": "value1"}', '{"result": "ascii_success"}')
    
#     arguments = {"param1": "value1"}
#     result = await tcp_transport.call_tool("test_tool", arguments, provider_ascii)
    
#     assert result == '{"result": "ascii_success"}'
#     assert isinstance(result, str)
