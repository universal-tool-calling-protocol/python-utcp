"""
Tests for the MCP transport interface with HTTP transport.
"""
import sys
import pytest
import pytest_asyncio
import asyncio
import subprocess
import time
import os
import socket
from typing import List, Optional, Tuple

from utcp.client.transport_interfaces.mcp_transport import MCPTransport
from utcp.shared.provider import MCPProvider, McpConfig, McpHttpServer

HTTP_SERVER_NAME = "mock_http_server"
HTTP_SERVER_PORT = 8000


@pytest_asyncio.fixture
async def http_server_process() -> subprocess.Popen:
    """Start the HTTP MCP server as a separate process."""
    server_path = os.path.join(
        os.path.dirname(__file__), "mock_http_mcp_server.py"
    )
    process = subprocess.Popen(
        [sys.executable, server_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for the server to be ready by checking if the port is accessible and server logs
    server_ready = False
    for _ in range(30):  # Wait up to 30 seconds
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(("127.0.0.1", HTTP_SERVER_PORT))
                if result == 0:
                    # Also check if we can see the server startup message
                    server_ready = True
                    break
        except Exception:
            pass
        await asyncio.sleep(1)
    
    if not server_ready:
        # Server didn't start in time
        process.terminate()
        stdout, stderr = process.communicate()
        raise RuntimeError(f"HTTP server failed to start. stdout: {stdout.decode()}, stderr: {stderr.decode()}")
    
    # Give the server a bit more time to fully initialize
    await asyncio.sleep(2)
    
    yield process
    
    # Clean up the process
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@pytest_asyncio.fixture
def http_mcp_provider() -> MCPProvider:
    """Provides an MCPProvider configured to connect to the mock HTTP server."""
    server_config = McpHttpServer(
        url=f"http://127.0.0.1:{HTTP_SERVER_PORT}/mcp",
        transport="http"
    )
    return MCPProvider(
        name="mock_http_provider",
        provider_type="mcp",
        config=McpConfig(mcpServers={HTTP_SERVER_NAME: server_config})
    )


@pytest_asyncio.fixture
async def transport() -> MCPTransport:
    """Provides a clean MCPTransport instance."""
    t = MCPTransport()
    yield t
    await t.close()


@pytest.mark.asyncio
async def test_http_register_provider_discovers_tools(
    transport: MCPTransport,
    http_mcp_provider: MCPProvider,
    http_server_process: subprocess.Popen
):
    """Test that registering an HTTP MCP provider discovers the correct tools."""
    tools = await transport.register_tool_provider(http_mcp_provider)
    assert len(tools) == 4
    
    # Find the echo tool
    echo_tool = next((tool for tool in tools if tool.name == "echo"), None)
    assert echo_tool is not None
    assert "echoes back its input" in echo_tool.description
    
    # Check for other tools
    tool_names = [tool.name for tool in tools]
    assert "greet" in tool_names
    assert "list_items" in tool_names
    assert "add_numbers" in tool_names


@pytest.mark.asyncio
async def test_http_structured_output(
    transport: MCPTransport,
    http_mcp_provider: MCPProvider,
    http_server_process: subprocess.Popen
):
    """Test that HTTP MCP tools with structured output work correctly."""
    # Register the provider
    await transport.register_tool_provider(http_mcp_provider)
    
    # Call the echo tool and verify the result
    result = await transport.call_tool("echo", {"message": "http_test"}, http_mcp_provider)
    assert result == {"reply": "you said: http_test"}


@pytest.mark.asyncio
async def test_http_unstructured_output(
    transport: MCPTransport,
    http_mcp_provider: MCPProvider,
    http_server_process: subprocess.Popen
):
    """Test that HTTP MCP tools with unstructured output types work correctly."""
    # Register the provider
    await transport.register_tool_provider(http_mcp_provider)
    
    # Call the greet tool and verify the result
    result = await transport.call_tool("greet", {"name": "Alice"}, http_mcp_provider)
    assert result == "Hello, Alice!"


@pytest.mark.asyncio
async def test_http_list_output(
    transport: MCPTransport,
    http_mcp_provider: MCPProvider,
    http_server_process: subprocess.Popen
):
    """Test that HTTP MCP tools returning lists work correctly."""
    # Register the provider
    await transport.register_tool_provider(http_mcp_provider)
    
    # Call the list_items tool and verify the result
    result = await transport.call_tool("list_items", {"count": 3}, http_mcp_provider)
    
    # The result might be wrapped in a "result" field or returned directly
    if isinstance(result, dict) and "result" in result:
        items = result["result"]
    else:
        items = result
        
    assert isinstance(items, list)
    assert len(items) == 3
    assert items[0] == "item_0"
    assert items[1] == "item_1"
    assert items[2] == "item_2"


@pytest.mark.asyncio
async def test_http_numeric_output(
    transport: MCPTransport,
    http_mcp_provider: MCPProvider,
    http_server_process: subprocess.Popen
):
    """Test that HTTP MCP tools returning numeric values work correctly."""
    # Register the provider
    await transport.register_tool_provider(http_mcp_provider)
    
    # Call the add_numbers tool and verify the result
    result = await transport.call_tool("add_numbers", {"a": 5, "b": 7}, http_mcp_provider)
    
    # The result might be wrapped in a "result" field or returned directly
    if isinstance(result, dict) and "result" in result:
        value = result["result"]
    else:
        value = result
        
    assert value == 12


@pytest.mark.asyncio
async def test_http_deregister_provider(
    transport: MCPTransport,
    http_mcp_provider: MCPProvider,
    http_server_process: subprocess.Popen
):
    """Test that deregistering an HTTP MCP provider works (no-op in session-per-operation mode)."""
    # Register a provider
    tools = await transport.register_tool_provider(http_mcp_provider)
    assert len(tools) == 4
    
    # Deregister it (this is a no-op in session-per-operation mode)
    await transport.deregister_tool_provider(http_mcp_provider)
    
    # Should still be able to call tools since we create fresh sessions
    result = await transport.call_tool("echo", {"message": "test"}, http_mcp_provider)
    assert result == {"reply": "you said: test"}
