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
def mcp_manual_with_resources() -> McpCallTemplate:
    """Provides an McpCallTemplate with resources enabled."""
    server_path = os.path.join(os.path.dirname(__file__), "mock_mcp_server.py")
    server_config = {
        "command": sys.executable,
        "args": [server_path],
    }
    return McpCallTemplate(
        name="mock_mcp_manual_with_resources",
        call_template_type="mcp",
        config=McpConfig(mcpServers={SERVER_NAME: server_config}),
        register_resources_as_tools=True
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
    echo_tool = next((tool for tool in register_result.manual.tools if tool.name == f"{SERVER_NAME}.echo"), None)
    assert echo_tool is not None
    assert "echoes back its input" in echo_tool.description

    # Check for other tools
    tool_names = [tool.name for tool in register_result.manual.tools]
    assert f"{SERVER_NAME}.greet" in tool_names
    assert f"{SERVER_NAME}.list_items" in tool_names
    assert f"{SERVER_NAME}.add_numbers" in tool_names


@pytest.mark.asyncio
async def test_call_tool_succeeds(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Verify a successful tool call after registration."""
    await transport.register_manual(None, mcp_manual)

    result = await transport.call_tool(None, f"{SERVER_NAME}.echo", {"message": "test"}, mcp_manual)

    assert result == {"reply": "you said: test"}


@pytest.mark.asyncio
async def test_call_tool_works_without_register(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Verify that calling a tool works without prior registration in session-per-operation mode."""
    result = await transport.call_tool(None, f"{SERVER_NAME}.echo", {"message": "test"}, mcp_manual)
    assert result == {"reply": "you said: test"}


@pytest.mark.asyncio
async def test_structured_output_tool(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Test that tools with structured output (TypedDict) work correctly."""
    await transport.register_manual(None, mcp_manual)

    result = await transport.call_tool(None, f"{SERVER_NAME}.echo", {"message": "test"}, mcp_manual)
    assert result == {"reply": "you said: test"}


@pytest.mark.asyncio
async def test_unstructured_string_output(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Test that tools returning plain strings work correctly."""
    await transport.register_manual(None, mcp_manual)

    result = await transport.call_tool(None, f"{SERVER_NAME}.greet", {"name": "Alice"}, mcp_manual)
    assert result == "Hello, Alice!"


@pytest.mark.asyncio
async def test_list_output(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Test that tools returning lists work correctly."""
    await transport.register_manual(None, mcp_manual)

    result = await transport.call_tool(None, f"{SERVER_NAME}.list_items", {"count": 3}, mcp_manual)

    assert isinstance(result, list)
    assert len(result) == 3
    assert result == ["item_0", "item_1", "item_2"]


@pytest.mark.asyncio
async def test_numeric_output(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Test that tools returning numeric values work correctly."""
    await transport.register_manual(None, mcp_manual)

    result = await transport.call_tool(None, f"{SERVER_NAME}.add_numbers", {"a": 5, "b": 7}, mcp_manual)

    assert result == 12


@pytest.mark.asyncio
async def test_deregister_manual(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Verify that deregistering a manual works (no-op in session-per-operation mode)."""
    register_result = await transport.register_manual(None, mcp_manual)
    assert register_result.success
    assert len(register_result.manual.tools) == 4

    await transport.deregister_manual(None, mcp_manual)

    result = await transport.call_tool(None, f"{SERVER_NAME}.echo", {"message": "test"}, mcp_manual)
    assert result == {"reply": "you said: test"}


@pytest.mark.asyncio
async def test_register_resources_as_tools_disabled(transport: McpCommunicationProtocol, mcp_manual: McpCallTemplate):
    """Verify that resources are NOT registered as tools when flag is False (default)."""
    register_result = await transport.register_manual(None, mcp_manual)
    assert register_result.success
    assert len(register_result.manual.tools) == 4  # Only the regular tools

    # Check that no resource tools are present
    tool_names = [tool.name for tool in register_result.manual.tools]
    resource_tools = [name for name in tool_names if name.startswith(f"{SERVER_NAME}.resource_")]
    assert len(resource_tools) == 0


@pytest.mark.asyncio
async def test_register_resources_as_tools_enabled(transport: McpCommunicationProtocol, mcp_manual_with_resources: McpCallTemplate):
    """Verify that resources are registered as tools when flag is True."""
    register_result = await transport.register_manual(None, mcp_manual_with_resources)
    assert register_result.success
    
    # Should have 4 regular tools + 2 resource tools = 6 total
    assert len(register_result.manual.tools) >= 6

    # Check that resource tools are present
    tool_names = [tool.name for tool in register_result.manual.tools]
    resource_tools = [name for name in tool_names if name.startswith(f"{SERVER_NAME}.resource_")]
    assert len(resource_tools) == 2
    assert f"{SERVER_NAME}.resource_get_test_document" in resource_tools
    assert f"{SERVER_NAME}.resource_get_config" in resource_tools

    # Check resource tool properties
    test_doc_tool = next((tool for tool in register_result.manual.tools if tool.name == f"{SERVER_NAME}.resource_get_test_document"), None)
    assert test_doc_tool is not None
    assert "Read resource:" in test_doc_tool.description
    assert "file://test_document.txt" in test_doc_tool.description


@pytest.mark.asyncio
async def test_call_resource_tool(transport: McpCommunicationProtocol, mcp_manual_with_resources: McpCallTemplate):
    """Verify that calling a resource tool returns the resource content."""
    # Register the manual with resources
    await transport.register_manual(None, mcp_manual_with_resources)

    # Call the test document resource
    result = await transport.call_tool(None, f"{SERVER_NAME}.resource_get_test_document", {}, mcp_manual_with_resources)
    
    # Check that we get the resource content
    assert isinstance(result, dict)
    assert "contents" in result
    contents = result["contents"]
    
    # The content should contain the test document text
    found_test_content = False
    for content_item in contents:
        if isinstance(content_item, dict) and "text" in content_item:
            if "This is a test document" in content_item["text"]:
                found_test_content = True
                break
        elif isinstance(content_item, str) and "This is a test document" in content_item:
            found_test_content = True
            break
    
    assert found_test_content, f"Expected test document content not found in: {contents}"


@pytest.mark.asyncio
async def test_call_resource_tool_json_content(transport: McpCommunicationProtocol, mcp_manual_with_resources: McpCallTemplate):
    """Verify that calling a JSON resource tool returns the structured content."""
    # Register the manual with resources
    await transport.register_manual(None, mcp_manual_with_resources)

    # Call the config.json resource
    result = await transport.call_tool(None, f"{SERVER_NAME}.resource_get_config", {}, mcp_manual_with_resources)
    
    # Check that we get the resource content
    assert isinstance(result, dict)
    assert "contents" in result
    contents = result["contents"]
    
    # The content should contain the JSON config
    found_json_content = False
    for content_item in contents:
        if isinstance(content_item, dict) and "text" in content_item:
            if "test_config" in content_item["text"]:
                found_json_content = True
                break
        elif isinstance(content_item, str) and "test_config" in content_item:
            found_json_content = True
            break
    
    assert found_json_content, f"Expected JSON content not found in: {contents}"


@pytest.mark.asyncio
async def test_call_nonexistent_resource_tool(transport: McpCommunicationProtocol, mcp_manual_with_resources: McpCallTemplate):
    """Verify that calling a non-existent resource tool raises an error."""
    with pytest.raises(ValueError, match="Resource 'nonexistent' not found in any configured server"):
        await transport.call_tool(None, f"{SERVER_NAME}.resource_nonexistent", {}, mcp_manual_with_resources)


@pytest.mark.asyncio
async def test_resource_tool_without_registration(transport: McpCommunicationProtocol, mcp_manual_with_resources: McpCallTemplate):
    """Verify that resource tools work even without prior registration."""
    # Don't register the manual first - test direct call
    result = await transport.call_tool(None, f"{SERVER_NAME}.resource_get_test_document", {}, mcp_manual_with_resources)
    
    # Should still work and return content
    assert isinstance(result, dict)
    assert "contents" in result
