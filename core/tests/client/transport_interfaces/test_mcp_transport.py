import sys
import pytest
import pytest_asyncio
import asyncio

from utcp.client.transport_interfaces.mcp_transport import MCPTransport
from utcp.shared.provider import MCPProvider, McpConfig, McpStdioServer

SERVER_NAME = "mock_stdio_server"

@pytest_asyncio.fixture
def mcp_provider() -> MCPProvider:
    """Provides an MCPProvider configured to run the mock stdio server."""
    server_config = McpStdioServer(
        command=sys.executable,
        args=["tests/client/transport_interfaces/mock_mcp_server.py"],
    )
    return MCPProvider(
        name="mock_mcp_provider",
        provider_type="mcp",
        config=McpConfig(mcpServers={SERVER_NAME: server_config})
    )

@pytest_asyncio.fixture
async def transport() -> MCPTransport:
    """Provides a clean MCPTransport instance."""
    t = MCPTransport()
    yield t
    await t.close()

@pytest.mark.asyncio
async def test_register_provider_discovers_tools(transport: MCPTransport, mcp_provider: MCPProvider):
    """Verify that registering a provider discovers the correct tools."""
    tools = await transport.register_tool_provider(mcp_provider)
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
async def test_call_tool_succeeds(transport: MCPTransport, mcp_provider: MCPProvider):
    """Verify a successful tool call after registration."""
    await transport.register_tool_provider(mcp_provider)
    
    result = await transport.call_tool("echo", {"message": "test"}, mcp_provider)
    
    assert result == {"reply": "you said: test"}

@pytest.mark.asyncio
async def test_call_tool_works_without_register(transport: MCPTransport, mcp_provider: MCPProvider):
    """Verify that calling a tool works without prior registration in session-per-operation mode."""
    # In session-per-operation mode, registration is not required
    result = await transport.call_tool("echo", {"message": "test"}, mcp_provider)
    assert result == {"reply": "you said: test"}

@pytest.mark.asyncio
async def test_structured_output_tool(transport: MCPTransport, mcp_provider: MCPProvider):
    """Test that tools with structured output (TypedDict) work correctly."""
    # Register the provider
    await transport.register_tool_provider(mcp_provider)
    
    # Call the echo tool and verify the result
    result = await transport.call_tool("echo", {"message": "test"}, mcp_provider)
    assert result == {"reply": "you said: test"}

@pytest.mark.asyncio
async def test_unstructured_string_output(transport: MCPTransport, mcp_provider: MCPProvider):
    """Test that tools returning plain strings work correctly."""
    # Register the provider
    await transport.register_tool_provider(mcp_provider)
    
    # Call the greet tool which returns a plain string
    result = await transport.call_tool("greet", {"name": "Alice"}, mcp_provider)
    assert result == "Hello, Alice!"

@pytest.mark.asyncio
async def test_list_output(transport: MCPTransport, mcp_provider: MCPProvider):
    """Test that tools returning lists work correctly."""
    # Register the provider
    await transport.register_tool_provider(mcp_provider)
    
    # Call the list_items tool
    result = await transport.call_tool("list_items", {"count": 3}, mcp_provider)
    
    # The result should be a list or wrapped in a result field
    if isinstance(result, dict) and "result" in result:
        items = result["result"]
    else:
        items = result
        
    assert isinstance(items, list)
    assert len(items) == 3
    assert items == ["item_0", "item_1", "item_2"]

@pytest.mark.asyncio
async def test_numeric_output(transport: MCPTransport, mcp_provider: MCPProvider):
    """Test that tools returning numeric values work correctly."""
    # Register the provider
    await transport.register_tool_provider(mcp_provider)
    
    # Call the add_numbers tool
    result = await transport.call_tool("add_numbers", {"a": 5, "b": 7}, mcp_provider)
    
    # The result should be a number or wrapped in a result field
    if isinstance(result, dict) and "result" in result:
        value = result["result"]
    else:
        value = result
        
    assert value == 12

@pytest.mark.asyncio
async def test_deregister_provider(transport: MCPTransport, mcp_provider: MCPProvider):
    """Verify that deregistering a provider works (no-op in session-per-operation mode)."""
    # Register a provider
    tools = await transport.register_tool_provider(mcp_provider)
    assert len(tools) == 4
    
    # Deregister it (this is a no-op in session-per-operation mode)
    await transport.deregister_tool_provider(mcp_provider)
    
    # Should still be able to call tools since we create fresh sessions
    result = await transport.call_tool("echo", {"message": "test"}, mcp_provider)
    assert result == {"reply": "you said: test"}
