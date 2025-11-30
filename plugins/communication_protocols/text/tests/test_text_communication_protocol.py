"""
Tests for the Text communication protocol (direct content) implementation.
"""
import json
import pytest
import pytest_asyncio
from unittest.mock import Mock

from utcp_text.text_communication_protocol import TextCommunicationProtocol
from utcp_text.text_call_template import TextCallTemplate
from utcp.data.call_template import CallTemplate
from utcp.data.register_manual_response import RegisterManualResult
from utcp.data.auth_implementations.api_key_auth import ApiKeyAuth
from utcp.utcp_client import UtcpClient


@pytest_asyncio.fixture
async def text_protocol() -> TextCommunicationProtocol:
    """Provides a TextCommunicationProtocol instance."""
    yield TextCommunicationProtocol()


@pytest_asyncio.fixture
def mock_utcp_client() -> Mock:
    """Provides a mock UtcpClient."""
    client = Mock(spec=UtcpClient)
    client.root_dir = None
    return client


@pytest_asyncio.fixture
def sample_utcp_manual():
    """Sample UTCP manual with multiple tools."""
    return {
        "utcp_version": "1.0.0",
        "manual_version": "1.0.0",
        "tools": [
            {
                "name": "calculator",
                "description": "Performs basic arithmetic operations",
                "inputs": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["add", "subtract", "multiply", "divide"]
                        },
                        "a": {"type": "number"},
                        "b": {"type": "number"}
                    },
                    "required": ["operation", "a", "b"]
                },
                "outputs": {
                    "type": "object",
                    "properties": {
                        "result": {"type": "number"}
                    }
                },
                "tags": ["math", "arithmetic"],
                "tool_call_template": {
                    "call_template_type": "text",
                    "name": "test-text-call-template",
                    "content": "dummy content"
                }
            },
            {
                "name": "string_utils",
                "description": "String manipulation utilities",
                "inputs": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "operation": {
                            "type": "string",
                            "enum": ["uppercase", "lowercase", "reverse"]
                        }
                    },
                    "required": ["text", "operation"]
                },
                "outputs": {
                    "type": "object",
                    "properties": {
                        "result": {"type": "string"}
                    }
                },
                "tags": ["text", "utilities"],
                "tool_call_template": {
                    "call_template_type": "text",
                    "name": "test-text-call-template",
                    "content": "dummy content"
                }
            }
        ]
    }


@pytest.mark.asyncio
async def test_register_manual_with_utcp_manual(
    text_protocol: TextCommunicationProtocol, sample_utcp_manual, mock_utcp_client: Mock
):
    """Register a manual from direct content and validate returned tools."""
    content = json.dumps(sample_utcp_manual)
    manual_template = TextCallTemplate(name="test_manual", content=content)
    result = await text_protocol.register_manual(mock_utcp_client, manual_template)

    assert isinstance(result, RegisterManualResult)
    assert result.success is True
    assert result.errors == []
    assert result.manual is not None
    assert len(result.manual.tools) == 2

    tool0 = result.manual.tools[0]
    assert tool0.name == "calculator"
    assert tool0.description == "Performs basic arithmetic operations"
    assert tool0.tags == ["math", "arithmetic"]
    assert tool0.tool_call_template.call_template_type == "text"

    tool1 = result.manual.tools[1]
    assert tool1.name == "string_utils"
    assert tool1.description == "String manipulation utilities"
    assert tool1.tags == ["text", "utilities"]
    assert tool1.tool_call_template.call_template_type == "text"


@pytest.mark.asyncio
async def test_register_manual_with_yaml_content(
    text_protocol: TextCommunicationProtocol, mock_utcp_client: Mock
):
    """Register a manual from YAML content."""
    yaml_content = """
utcp_version: "1.0.0"
manual_version: "1.0.0"
tools:
  - name: yaml_tool
    description: A tool defined in YAML
    inputs:
      type: object
      properties: {}
    outputs:
      type: object
      properties: {}
    tags: []
    tool_call_template:
      call_template_type: text
      content: "test"
"""
    manual_template = TextCallTemplate(name="yaml_manual", content=yaml_content)
    result = await text_protocol.register_manual(mock_utcp_client, manual_template)

    assert result.success is True
    assert len(result.manual.tools) == 1
    assert result.manual.tools[0].name == "yaml_tool"


@pytest.mark.asyncio
async def test_register_manual_invalid_json(
    text_protocol: TextCommunicationProtocol, mock_utcp_client: Mock
):
    """Registering a manual with invalid content should return errors."""
    manual_template = TextCallTemplate(name="invalid", content="{ invalid json content }")
    result = await text_protocol.register_manual(mock_utcp_client, manual_template)
    assert isinstance(result, RegisterManualResult)
    assert result.success is False
    assert result.errors


@pytest.mark.asyncio
async def test_register_manual_wrong_call_template_type(text_protocol: TextCommunicationProtocol, mock_utcp_client: Mock):
    """Registering with a non-Text call template should raise ValueError."""
    wrong_template = CallTemplate(call_template_type="invalid", name="wrong")
    with pytest.raises(ValueError, match="requires a TextCallTemplate"):
        await text_protocol.register_manual(mock_utcp_client, wrong_template)


@pytest.mark.asyncio
async def test_call_tool_returns_content(
    text_protocol: TextCommunicationProtocol, sample_utcp_manual, mock_utcp_client: Mock
):
    """Calling a tool returns the content directly."""
    content = json.dumps(sample_utcp_manual)
    tool_template = TextCallTemplate(name="tool_call", content=content)

    # Call a tool should return the content directly
    result = await text_protocol.call_tool(
        mock_utcp_client, "calculator", {"operation": "add", "a": 1, "b": 2}, tool_template
    )

    # Verify we get the content back as-is
    assert isinstance(result, str)
    assert result == content


@pytest.mark.asyncio
async def test_call_tool_wrong_call_template_type(text_protocol: TextCommunicationProtocol, mock_utcp_client: Mock):
    """Calling a tool with wrong call template type should raise ValueError."""
    wrong_template = CallTemplate(call_template_type="invalid", name="wrong")
    with pytest.raises(ValueError, match="requires a TextCallTemplate"):
        await text_protocol.call_tool(mock_utcp_client, "some_tool", {}, wrong_template)


@pytest.mark.asyncio
async def test_deregister_manual(text_protocol: TextCommunicationProtocol, sample_utcp_manual, mock_utcp_client: Mock):
    """Deregistering a manual should be a no-op (no errors)."""
    content = json.dumps(sample_utcp_manual)
    manual_template = TextCallTemplate(name="test_manual", content=content)
    await text_protocol.deregister_manual(mock_utcp_client, manual_template)


@pytest.mark.asyncio
async def test_call_tool_streaming(text_protocol: TextCommunicationProtocol, sample_utcp_manual, mock_utcp_client: Mock):
    """Streaming call should yield a single chunk equal to non-streaming content."""
    content = json.dumps(sample_utcp_manual)
    tool_template = TextCallTemplate(name="tool_call", content=content)
    
    # Non-streaming
    result = await text_protocol.call_tool(mock_utcp_client, "calculator", {}, tool_template)
    # Streaming
    stream = text_protocol.call_tool_streaming(mock_utcp_client, "calculator", {}, tool_template)
    chunks = [c async for c in stream]
    assert chunks == [result]


@pytest.mark.asyncio
async def test_text_call_template_with_auth_tools():
    """Test that TextCallTemplate can be created with auth_tools."""
    auth_tools = ApiKeyAuth(api_key="test-key", var_name="Authorization", location="header")
    
    template = TextCallTemplate(
        name="test-template",
        content='{"test": true}',
        auth_tools=auth_tools
    )
    
    assert template.auth_tools == auth_tools
    assert template.auth is None


@pytest.mark.asyncio
async def test_text_call_template_with_base_url():
    """Test that TextCallTemplate can be created with base_url."""
    template = TextCallTemplate(
        name="test-template",
        content='{"openapi": "3.0.0"}',
        base_url="https://api.example.com/v1"
    )
    
    assert template.base_url == "https://api.example.com/v1"


@pytest.mark.asyncio
async def test_text_call_template_auth_tools_serialization():
    """Test that auth_tools field properly serializes and validates from dict."""
    # Test creation from dict
    template_dict = {
        "name": "test-template",
        "call_template_type": "text",
        "content": '{"test": true}',
        "auth_tools": {
            "auth_type": "api_key",
            "api_key": "test-key",
            "var_name": "Authorization",
            "location": "header"
        }
    }
    
    template = TextCallTemplate(**template_dict)
    assert template.auth_tools is not None
    assert template.auth_tools.api_key == "test-key"
    assert template.auth_tools.var_name == "Authorization"
    
    # Test serialization to dict
    serialized = template.model_dump()
    assert serialized["auth_tools"]["auth_type"] == "api_key"
    assert serialized["auth_tools"]["api_key"] == "test-key"
