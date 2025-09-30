# import pytest
# import pytest_asyncio
# import json
# import asyncio
# import socket
# from unittest.mock import MagicMock, patch, AsyncMock

# from utcp.client.transport_interfaces.udp_transport import UDPTransport
# from utcp.shared.provider import UDPProvider
# from utcp.shared.tool import Tool, ToolInputOutputSchema


# class MockUDPServer:
#     """Mock UDP server for testing."""
    
#     def __init__(self, host='localhost', port=0):
#         self.host = host
#         self.port = port
#         self.sock = None
#         self.running = False
#         self.responses = {}  # Map message -> response
#         self.call_count = 0
#         self.listen_task = None
        
#     async def start(self):
#         """Start the mock UDP server."""
#         # Create socket and bind
#         self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#         # Keep it blocking since we're using run_in_executor
#         self.sock.bind((self.host, self.port))
#         if self.port == 0:  # Auto-assign port
#             self.port = self.sock.getsockname()[1]
        
#         self.running = True
        
#         # Start listening task
#         self.listen_task = asyncio.create_task(self._listen())
        
#         # Give the server a moment to start
#         await asyncio.sleep(0.1)
        
#     async def stop(self):
#         """Stop the mock UDP server."""
#         self.running = False
#         if self.listen_task:
#             self.listen_task.cancel()
#             try:
#                 await self.listen_task
#             except asyncio.CancelledError:
#                 pass
#         if self.sock:
#             self.sock.close()
            
#     async def _listen(self):
#         """Listen for UDP messages and send responses."""
#         # Use a blocking approach with short timeout for responsiveness
#         self.sock.settimeout(0.01)  # Very short timeout
        
#         while self.running:
#             try:
#                 data, addr = self.sock.recvfrom(4096)
#                 self.call_count += 1
                
#                 try:
#                     message = data.decode('utf-8')
#                 except UnicodeDecodeError:
#                     message = data.hex()  # Fallback for binary data
                
#                 # Get response for this message
#                 response = self.responses.get(message, '{"error": "unknown_message"}')
                
#                 # Convert response to bytes
#                 if isinstance(response, str):
#                     response_bytes = response.encode('utf-8')
#                 elif isinstance(response, bytes):
#                     response_bytes = response
#                 elif isinstance(response, dict) or isinstance(response, list):
#                     response_bytes = json.dumps(response).encode('utf-8')
#                 else:
#                     response_bytes = str(response).encode('utf-8')
                
#                 # Send response back immediately
#                 self.sock.sendto(response_bytes, addr)
                
#             except socket.timeout:
#                 # Expected timeout, continue loop
#                 await asyncio.sleep(0.001)  # Brief async yield
#                 continue
#             except asyncio.CancelledError:
#                 break
#             except Exception as e:
#                 if self.running:  # Only log if we're still supposed to be running
#                     import traceback
#                     print(f"Mock UDP server error: {e}")
#                     print(f"Traceback: {traceback.format_exc()}")
#                 await asyncio.sleep(0.01)  # Brief pause before retrying
                
#     def set_response(self, message, response):
#         """Set a response for a specific message."""
#         self.responses[message] = response


# @pytest_asyncio.fixture
# async def mock_udp_server():
#     """Create a mock UDP server for testing."""
#     server = MockUDPServer()
#     await server.start()
#     yield server
#     await server.stop()


# @pytest.fixture
# def logger():
#     """Create a mock logger."""
#     return MagicMock()


# @pytest.fixture
# def udp_transport(logger):
#     """Create a UDP transport instance."""
#     return UDPTransport(logger=logger)


# @pytest.fixture
# def udp_provider(mock_udp_server):
#     """Create a basic UDP provider for testing."""
#     return UDPProvider(
#         name="test_udp_provider",
#         host=mock_udp_server.host,
#         port=mock_udp_server.port,
#         number_of_response_datagrams=1,
#         request_data_format="json",
#         response_byte_format="utf-8",
#         timeout=5000
#     )


# @pytest.fixture
# def text_template_provider(mock_udp_server):
#     """Create a UDP provider with text template format."""
#     return UDPProvider(
#         name="test_text_template_provider",
#         host=mock_udp_server.host,
#         port=mock_udp_server.port,
#         number_of_response_datagrams=1,
#         request_data_format="text",
#         request_data_template="COMMAND UTCP_ARG_action_UTCP_ARG UTCP_ARG_value_UTCP_ARG",
#         response_byte_format="utf-8",
#         timeout=5000
#     )


# @pytest.fixture
# def raw_bytes_provider(mock_udp_server):
#     """Create a UDP provider that returns raw bytes."""
#     return UDPProvider(
#         name="test_raw_bytes_provider",
#         host=mock_udp_server.host,
#         port=mock_udp_server.port,
#         number_of_response_datagrams=1,
#         request_data_format="json",
#         response_byte_format=None,  # Return raw bytes
#         timeout=5000
#     )


# @pytest.fixture
# def multi_datagram_provider(mock_udp_server):
#     """Create a UDP provider that expects multiple response datagrams."""
#     return UDPProvider(
#         name="test_multi_datagram_provider",
#         host=mock_udp_server.host,
#         port=mock_udp_server.port,
#         number_of_response_datagrams=3,
#         request_data_format="json",
#         response_byte_format="utf-8",
#         timeout=5000
#     )


# # Test register_tool_provider
# @pytest.mark.asyncio
# async def test_register_tool_provider(udp_transport, udp_provider, mock_udp_server, logger):
#     """Test registering a tool provider."""
#     # Set up discovery response
#     discovery_response = {
#         "tools": [
#             {
#                 "name": "test_tool",
#                 "description": "Test tool",
#                 "inputs": {
#                     "type": "object",
#                     "properties": {
#                         "param1": {"type": "string"}
#                     }
#                 },
#                 "outputs": {
#                     "type": "object",
#                     "properties": {
#                         "result": {"type": "string"}
#                     }
#                 },
#                 "tags": [],
#                 "tool_provider": {
#                     "provider_type": "udp",
#                     "name": "test_udp_provider",
#                     "host": "localhost",
#                     "port": udp_provider.port
#                 }
#             }
#         ]
#     }
    
#     mock_udp_server.set_response('{"type": "utcp"}', discovery_response)
#     print(f"Mock UDP server port: {mock_udp_server.port}")
#     print(f"UDP provider port: {udp_provider.port}")
    
#     # Register the provider
#     tools = await udp_transport.register_tool_provider(udp_provider)
    
#     # Verify tools were returned
#     assert len(tools) == 1
#     assert tools[0].name == "test_tool"
#     assert tools[0].description == "Test tool"
    
#     # Verify logger was called
#     logger.assert_called()


# @pytest.mark.asyncio
# async def test_register_tool_provider_empty_response(udp_transport, udp_provider, mock_udp_server):
#     """Test registering a tool provider with empty response."""
#     # Set up empty discovery response
#     mock_udp_server.set_response('{"type": "utcp"}', {"tools": []})
    
#     # Register the provider
#     tools = await udp_transport.register_tool_provider(udp_provider)
    
#     # Verify no tools were returned
#     assert len(tools) == 0


# @pytest.mark.asyncio
# async def test_register_tool_provider_invalid_json(udp_transport, udp_provider, mock_udp_server):
#     """Test registering a tool provider with invalid JSON response."""
#     # Set up invalid JSON response
#     mock_udp_server.set_response('{"type": "utcp"}', "invalid json")
    
#     # Register the provider
#     tools = await udp_transport.register_tool_provider(udp_provider)
    
#     # Verify no tools were returned due to JSON error
#     assert len(tools) == 0


# @pytest.mark.asyncio
# async def test_register_tool_provider_invalid_provider_type(udp_transport):
#     """Test registering a non-UDP provider raises ValueError."""
#     from utcp.shared.provider import HttpProvider
    
#     http_provider = HttpProvider(
#         name="test_http_provider",
#         url="http://example.com"
#     )
    
#     with pytest.raises(ValueError, match="UDPTransport can only be used with UDPProvider"):
#         await udp_transport.register_tool_provider(http_provider)


# # Test deregister_tool_provider
# @pytest.mark.asyncio
# async def test_deregister_tool_provider(udp_transport, udp_provider):
#     """Test deregistering a tool provider (should be a no-op)."""
#     # This should not raise any exceptions
#     await udp_transport.deregister_tool_provider(udp_provider)


# @pytest.mark.asyncio
# async def test_deregister_tool_provider_invalid_type(udp_transport):
#     """Test deregistering a non-UDP provider raises ValueError."""
#     from utcp.shared.provider import HttpProvider
    
#     http_provider = HttpProvider(
#         name="test_http_provider",
#         url="http://example.com"
#     )
    
#     with pytest.raises(ValueError, match="UDPTransport can only be used with UDPProvider"):
#         await udp_transport.deregister_tool_provider(http_provider)


# # Test call_tool with JSON format
# @pytest.mark.asyncio
# async def test_call_tool_json_format(udp_transport, udp_provider, mock_udp_server):
#     """Test calling a tool with JSON format."""
#     # Set up tool call response
#     arguments = {"param1": "value1", "param2": 42}
#     expected_message = json.dumps(arguments)
#     response = {"result": "success", "data": "processed"}
    
#     mock_udp_server.set_response(expected_message, response)
    
#     # Call the tool
#     result = await udp_transport.call_tool("test_tool", arguments, udp_provider)
    
#     # Verify response
#     assert result == json.dumps(response)
#     assert mock_udp_server.call_count >= 1


# @pytest.mark.asyncio
# async def test_call_tool_text_template_format(udp_transport, text_template_provider, mock_udp_server):
#     """Test calling a tool with text template format."""
#     # Set up tool call response
#     arguments = {"action": "get", "value": "data123"}
#     expected_message = "COMMAND get data123"  # Template substitution
#     response = "SUCCESS: data123 retrieved"
    
#     mock_udp_server.set_response(expected_message, response)
    
#     # Call the tool
#     result = await udp_transport.call_tool("test_tool", arguments, text_template_provider)
    
#     # Verify response
#     assert result == response
#     assert mock_udp_server.call_count >= 1


# @pytest.mark.asyncio
# async def test_call_tool_text_format_no_template(udp_transport, mock_udp_server):
#     """Test calling a tool with text format but no template."""
#     provider = UDPProvider(
#         name="test_provider",
#         host=mock_udp_server.host,
#         port=mock_udp_server.port,
#         request_data_format="text",
#         request_data_template=None,  # No template
#         response_byte_format="utf-8",
#         number_of_response_datagrams=1  # Expect 1 response
#     )
    
#     # Set up tool call response
#     arguments = {"param1": "value1", "param2": "value2"}
#     expected_message = "value1 value2"  # Fallback format
#     response = "OK"
    
#     mock_udp_server.set_response(expected_message, response)
    
#     # Call the tool
#     result = await udp_transport.call_tool("test_tool", arguments, provider)
    
#     # Verify response
#     assert result == response


# @pytest.mark.asyncio
# async def test_call_tool_raw_bytes_response(udp_transport, raw_bytes_provider, mock_udp_server):
#     """Test calling a tool that returns raw bytes."""
#     # Set up tool call response with raw bytes
#     arguments = {"param1": "value1"}
#     expected_message = json.dumps(arguments)
#     raw_response = b"\x01\x02\x03\x04binary_data"
    
#     mock_udp_server.set_response(expected_message, raw_response)
    
#     # Call the tool
#     result = await udp_transport.call_tool("test_tool", arguments, raw_bytes_provider)
    
#     # Verify response is raw bytes
#     assert isinstance(result, bytes)
#     assert result == raw_response


# @pytest.mark.asyncio
# async def test_call_tool_invalid_provider_type(udp_transport):
#     """Test calling a tool with non-UDP provider raises ValueError."""
#     from utcp.shared.provider import HttpProvider
    
#     http_provider = HttpProvider(
#         name="test_http_provider",
#         url="http://example.com"
#     )
    
#     with pytest.raises(ValueError, match="UDPTransport can only be used with UDPProvider"):
#         await udp_transport.call_tool("test_tool", {"param": "value"}, http_provider)


# # Test multi-datagram support
# @pytest.mark.asyncio
# async def test_call_tool_multiple_datagrams(udp_transport, multi_datagram_provider, mock_udp_server):
#     """Test calling a tool that expects multiple response datagrams."""
#     # This test is complex because we need to simulate multiple UDP responses
#     # For now, let's test that the transport handles the configuration correctly
    
#     # Mock the _send_udp_message method to simulate multiple datagram responses
#     with patch.object(udp_transport, '_send_udp_message') as mock_send:
#         mock_send.return_value = "part1part2part3"  # Concatenated response
        
#         arguments = {"param1": "value1"}
#         result = await udp_transport.call_tool("test_tool", arguments, multi_datagram_provider)
        
#         # Verify the method was called with correct parameters
#         mock_send.assert_called_once_with(
#             multi_datagram_provider.host,
#             multi_datagram_provider.port,
#             json.dumps(arguments),
#             multi_datagram_provider.timeout / 1000.0,
#             3,  # number_of_response_datagrams
#             "utf-8"  # response_byte_format
#         )
        
#         assert result == "part1part2part3"


# # Test _send_udp_message method directly
# @pytest.mark.asyncio
# async def test_send_udp_message_single_datagram(udp_transport, mock_udp_server):
#     """Test sending a UDP message and receiving a single response."""
#     # Set up response
#     message = "test message"
#     response = "test response"
#     mock_udp_server.set_response(message, response)
    
#     # Send message
#     result = await udp_transport._send_udp_message(
#         mock_udp_server.host,
#         mock_udp_server.port,
#         message,
#         timeout=5.0,
#         num_response_datagrams=1,
#         response_encoding="utf-8"
#     )
    
#     # Verify response
#     assert result == response


# @pytest.mark.asyncio
# async def test_send_udp_message_raw_bytes(udp_transport, mock_udp_server):
#     """Test sending a UDP message and receiving raw bytes."""
#     # Set up binary response
#     message = "test message"
#     response = b"\x01\x02\x03binary"
#     mock_udp_server.set_response(message, response)
    
#     # Send message with no encoding (raw bytes)
#     result = await udp_transport._send_udp_message(
#         mock_udp_server.host,
#         mock_udp_server.port,
#         message,
#         timeout=5.0,
#         num_response_datagrams=1,
#         response_encoding=None
#     )
    
#     # Verify response is bytes
#     assert isinstance(result, bytes)
#     assert result == response


# @pytest.mark.asyncio
# async def test_send_udp_message_timeout():
#     """Test UDP message timeout handling."""
#     udp_transport = UDPTransport()
    
#     # Try to send to a non-existent server (should timeout)
#     with pytest.raises(Exception):  # Should raise socket timeout or connection error
#         await udp_transport._send_udp_message(
#             "127.0.0.1",
#             99999,  # Non-existent port
#             "test message",
#             timeout=0.1,  # Very short timeout
#             num_response_datagrams=1,
#             response_encoding="utf-8"
#         )


# # Test _format_tool_call_message method
# def test_format_tool_call_message_json(udp_transport):
#     """Test formatting tool call message with JSON format."""
#     provider = UDPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         request_data_format="json"
#     )
    
#     arguments = {"param1": "value1", "param2": 42}
#     result = udp_transport._format_tool_call_message(arguments, provider)
    
#     # Should return JSON string
#     assert result == json.dumps(arguments)
    
#     # Verify it's valid JSON
#     parsed = json.loads(result)
#     assert parsed == arguments


# def test_format_tool_call_message_text_with_template(udp_transport):
#     """Test formatting tool call message with text template."""
#     provider = UDPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         request_data_format="text",
#         request_data_template="ACTION UTCP_ARG_cmd_UTCP_ARG PARAM UTCP_ARG_value_UTCP_ARG"
#     )
    
#     arguments = {"cmd": "get", "value": "data123"}
#     result = udp_transport._format_tool_call_message(arguments, provider)
    
#     # Should substitute placeholders
#     assert result == "ACTION get PARAM data123"


# def test_format_tool_call_message_text_with_complex_values(udp_transport):
#     """Test formatting tool call message with complex values in template."""
#     provider = UDPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         request_data_format="text",
#         request_data_template="DATA UTCP_ARG_obj_UTCP_ARG"
#     )
    
#     arguments = {"obj": {"nested": "value", "number": 123}}
#     result = udp_transport._format_tool_call_message(arguments, provider)
    
#     # Should JSON-serialize complex values
#     assert result == 'DATA {"nested": "value", "number": 123}'


# def test_format_tool_call_message_text_no_template(udp_transport):
#     """Test formatting tool call message with text format but no template."""
#     provider = UDPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         request_data_format="text",
#         request_data_template=None
#     )
    
#     arguments = {"param1": "value1", "param2": "value2"}
#     result = udp_transport._format_tool_call_message(arguments, provider)
    
#     # Should use fallback format (space-separated values)
#     assert result == "value1 value2"


# def test_format_tool_call_message_default_to_json(udp_transport):
#     """Test formatting tool call message defaults to JSON for unknown format."""
#     # Create a provider with valid format first
#     provider = UDPProvider(
#         name="test",
#         host="localhost",
#         port=1234,
#         request_data_format="json"
#     )
    
#     # Manually set an invalid format to test the fallback behavior
#     provider.request_data_format = "unknown"  # Invalid format
    
#     arguments = {"param1": "value1"}
#     result = udp_transport._format_tool_call_message(arguments, provider)
    
#     # Should default to JSON
#     assert result == json.dumps(arguments)


# # Test error handling and edge cases
# @pytest.mark.asyncio
# async def test_call_tool_server_error(udp_transport, udp_provider, mock_udp_server):
#     """Test handling server errors during tool calls."""
#     # Don't set any response, so the server will return an error
#     arguments = {"param1": "value1"}
    
#     # Call the tool - should get the default error response
#     result = await udp_transport.call_tool("test_tool", arguments, udp_provider)
    
#     # Should receive the default error message
#     assert '{"error": "unknown_message"}' in result


# @pytest.mark.asyncio
# async def test_register_tool_provider_malformed_tool(udp_transport, udp_provider, mock_udp_server):
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
    
#     mock_udp_server.set_response('{"type": "utcp"}', discovery_response)
    
#     # Register the provider - should handle invalid tool gracefully
#     tools = await udp_transport.register_tool_provider(udp_provider)
    
#     # Should return empty list due to invalid tool definition
#     assert len(tools) == 0


# # Test logging functionality
# @pytest.mark.asyncio
# async def test_logging_calls(udp_transport, udp_provider, mock_udp_server, logger):
#     """Test that logging functions are called appropriately."""
#     # Set up discovery response
#     discovery_response = {"tools": []}
#     mock_udp_server.set_response('{"type": "utcp"}', discovery_response)
    
#     # Register provider
#     await udp_transport.register_tool_provider(udp_provider)
    
#     # Verify logger was called
#     logger.assert_called()
    
#     # Call tool
#     mock_udp_server.set_response('{}', {"result": "test"})
#     await udp_transport.call_tool("test_tool", {}, udp_provider)
    
#     # Logger should have been called multiple times
#     assert logger.call_count > 1
