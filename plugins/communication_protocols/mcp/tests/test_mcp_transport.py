import sys
import os
import pytest
import pytest_asyncio

from utcp_mcp.mcp_communication_protocol import McpCommunicationProtocol
from utcp_mcp.mcp_call_template import McpCallTemplate, McpConfig

SERVER_NAME = "mock_stdio_server"


@pytest_asyncio.fixture
def mcp_manual() -> McpCallTemplate:
    """Provides an McpCallTemplate configured to run the mock stdio server."""
    server_path = os.path.join(os.path.dirname(__file__), "mock_mcp_server.py")
    server_config = {
        "command": sys.executable,
        "args": [server_path],
    }
    return McpCallTemplate(
        name="mock_mcp_manual",
        call_template_type="mcp",
        config=McpConfig(mcpServers={SERVER_NAME: server_config})
    )


@pytest_asyncio.fixture
async def transport() -> McpCommunicationProtocol:
    """Provides a clean McpCommunicationProtocol instance."""
    t = McpCommunicationProtocol()
    yield t


@pytest.mark.asyncio
async def test_register_manual_discovers_tools(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Verify that registering a manual discovers the correct tools."""
    register_result = await transport.register_manual(None, mcp_manual)
    assert register_result.success
    assert len(register_result.manual.tools) == 4

    # Find the echo tool
    echo_tool = next((tool for tool in register_result.manual.tools if tool.name == "echo"), None)
    assert echo_tool is not None
    assert "echoes back its input" in echo_tool.description

    # Check for other tools
    tool_names = [tool.name for tool in register_result.manual.tools]
    assert "greet" in tool_names
    assert "list_items" in tool_names
    assert "add_numbers" in tool_names


@pytest.mark.asyncio
async def test_call_tool_succeeds(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Verify a successful tool call after registration."""
    await transport.register_manual(None, mcp_manual)

    result = await transport.call_tool(None, "echo", {"message": "test"}, mcp_manual)

    assert result == {"reply": "you said: test"}


@pytest.mark.asyncio
async def test_call_tool_works_without_register(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Verify that calling a tool works without prior registration in session-per-operation mode."""
    result = await transport.call_tool(None, "echo", {"message": "test"}, mcp_manual)
    assert result == {"reply": "you said: test"}


@pytest.mark.asyncio
async def test_structured_output_tool(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Test that tools with structured output (TypedDict) work correctly."""
    await transport.register_manual(None, mcp_manual)

    result = await transport.call_tool(None, "echo", {"message": "test"}, mcp_manual)
    assert result == {"reply": "you said: test"}


@pytest.mark.asyncio
async def test_unstructured_string_output(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Test that tools returning plain strings work correctly."""
    await transport.register_manual(None, mcp_manual)

    result = await transport.call_tool(None, "greet", {"name": "Alice"}, mcp_manual)
    assert result == "Hello, Alice!"


@pytest.mark.asyncio
async def test_list_output(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Test that tools returning lists work correctly."""
    await transport.register_manual(None, mcp_manual)

    result = await transport.call_tool(None, "list_items", {"count": 3}, mcp_manual)

    assert isinstance(result, list)
    assert len(result) == 3
    assert result == ["item_0", "item_1", "item_2"]


@pytest.mark.asyncio
async def test_numeric_output(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Test that tools returning numeric values work correctly."""
    await transport.register_manual(None, mcp_manual)

    result = await transport.call_tool(None, "add_numbers", {"a": 5, "b": 7}, mcp_manual)

    assert result == 12


@pytest.mark.asyncio
async def test_deregister_manual(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Verify that deregistering a manual works (no-op in session-per-operation mode)."""
    register_result = await transport.register_manual(None, mcp_manual)
    assert register_result.success
    assert len(register_result.manual.tools) == 4

    await transport.deregister_manual(None, mcp_manual)

    result = await transport.call_tool(None, "echo", {"message": "test"}, mcp_manual)
    assert result == {"reply": "you said: test"}
