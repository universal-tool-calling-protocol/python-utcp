"""
Tests for the Text communication protocol (file-based) implementation.
"""
import json
import tempfile
from pathlib import Path
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
def mock_utcp_client(tmp_path: Path) -> Mock:
    """Provides a mock UtcpClient with a root_dir."""
    client = Mock(spec=UtcpClient)
    client.root_dir = tmp_path
    return client


@pytest_asyncio.fixture
def sample_utcp_manual():
    """Sample UTCP manual with multiple tools (new UTCP format)."""
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
                    "file_path": "dummy.json"
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
                    "file_path": "dummy.json"
                }
            }
        ]
    }


@pytest_asyncio.fixture
def single_tool_definition():
    """Sample single tool definition (new UTCP format)."""
    return {
        "name": "echo",
        "description": "Echoes back the input text",
        "inputs": {
            "type": "object",
            "properties": {
                "message": {"type": "string"}
            },
            "required": ["message"]
        },
        "outputs": {
            "type": "object",
            "properties": {
                "echo": {"type": "string"}
            }
        },
        "tags": ["utility"],
        "tool_call_template": {
            "call_template_type": "text",
            "name": "test-text-call-template",
            "file_path": "dummy.json"
        }
    }


@pytest_asyncio.fixture
def tool_array():
    """Sample array of tool definitions (new UTCP format)."""
    return [
        {
            "name": "tool1",
            "description": "First tool",
            "inputs": {"type": "object", "properties": {}, "required": []},
            "outputs": {"type": "object", "properties": {}, "required": []},
            "tags": [],
            "tool_call_template": {
                "call_template_type": "text",
                "name": "test-text-call-template",
                "file_path": "dummy.json"
            }
        },
        {
            "name": "tool2",
            "description": "Second tool",
            "inputs": {"type": "object", "properties": {}, "required": []},
            "outputs": {"type": "object", "properties": {}, "required": []},
            "tags": [],
            "tool_call_template": {
                "call_template_type": "text",
                "name": "test-text-call-template",
                "file_path": "dummy.json"
            }
        }
    ]


@pytest.mark.asyncio
async def test_register_manual_with_utcp_manual(
    text_protocol: TextCommunicationProtocol, sample_utcp_manual, mock_utcp_client: Mock
):
    """Register a manual from a local file and validate returned tools."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_utcp_manual, f)
        temp_file = f.name

    try:
        manual_template = TextCallTemplate(name="test_manual", file_path=temp_file)
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
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_register_manual_with_single_tool(
    text_protocol: TextCommunicationProtocol, single_tool_definition, mock_utcp_client: Mock
):
    """Register a manual with a single tool definition."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        manual = {
            "utcp_version": "1.0.0",
            "manual_version": "1.0.0",
            "tools": [single_tool_definition],
        }
        json.dump(manual, f)
        temp_file = f.name

    try:
        manual_template = TextCallTemplate(name="single_tool_manual", file_path=temp_file)
        result = await text_protocol.register_manual(mock_utcp_client, manual_template)

        assert result.success is True
        assert len(result.manual.tools) == 1
        tool = result.manual.tools[0]
        assert tool.name == "echo"
        assert tool.description == "Echoes back the input text"
        assert tool.tags == ["utility"]
        assert tool.tool_call_template.call_template_type == "text"
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_register_manual_with_tool_array(
    text_protocol: TextCommunicationProtocol, tool_array, mock_utcp_client: Mock
):
    """Register a manual with an array of tool definitions."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        manual = {
            "utcp_version": "1.0.0",
            "manual_version": "1.0.0",
            "tools": tool_array,
        }
        json.dump(manual, f)
        temp_file = f.name

    try:
        manual_template = TextCallTemplate(name="tool_array_manual", file_path=temp_file)
        result = await text_protocol.register_manual(mock_utcp_client, manual_template)

        assert result.success is True
        assert len(result.manual.tools) == 2
        assert result.manual.tools[0].name == "tool1"
        assert result.manual.tools[1].name == "tool2"
        assert result.manual.tools[0].tool_call_template.call_template_type == "text"
        assert result.manual.tools[1].tool_call_template.call_template_type == "text"
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_register_manual_file_not_found(
    text_protocol: TextCommunicationProtocol, mock_utcp_client: Mock
):
    """Registering a manual with a non-existent file should return errors."""
    manual_template = TextCallTemplate(name="missing", file_path="/path/that/does/not/exist.json")
    result = await text_protocol.register_manual(mock_utcp_client, manual_template)
    assert isinstance(result, RegisterManualResult)
    assert result.success is False
    assert result.errors


@pytest.mark.asyncio
async def test_register_manual_invalid_json(
    text_protocol: TextCommunicationProtocol, mock_utcp_client: Mock
):
    """Registering a manual with invalid JSON should return errors (no exception)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{ invalid json content }")
        temp_file = f.name

    try:
        manual_template = TextCallTemplate(name="invalid_json", file_path=temp_file)
        result = await text_protocol.register_manual(mock_utcp_client, manual_template)
        assert isinstance(result, RegisterManualResult)
        assert result.success is False
        assert result.errors
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_register_manual_wrong_call_template_type(text_protocol: TextCommunicationProtocol, mock_utcp_client: Mock):
    """Registering with a non-Text call template should raise ValueError."""
    wrong_template = CallTemplate(call_template_type="invalid", name="wrong")
    with pytest.raises(ValueError, match="requires a TextCallTemplate"):
        await text_protocol.register_manual(mock_utcp_client, wrong_template)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_call_tool_returns_file_content(
    text_protocol: TextCommunicationProtocol, sample_utcp_manual, mock_utcp_client: Mock
):
    """Calling a tool returns the file content from the call template path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_utcp_manual, f)
        temp_file = f.name

    try:
        tool_template = TextCallTemplate(name="tool_call", file_path=temp_file)

        # Call a tool should return the file content
        content = await text_protocol.call_tool(
            mock_utcp_client, "calculator", {"operation": "add", "a": 1, "b": 2}, tool_template
        )

        # Verify we get the JSON content back as a string
        assert isinstance(content, str)
        # Parse it back to verify it's the same content
        parsed_content = json.loads(content)
        assert parsed_content == sample_utcp_manual
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_call_tool_wrong_call_template_type(text_protocol: TextCommunicationProtocol, mock_utcp_client: Mock):
    """Calling a tool with wrong call template type should raise ValueError."""
    wrong_template = CallTemplate(call_template_type="invalid", name="wrong")
    with pytest.raises(ValueError, match="requires a TextCallTemplate"):
        await text_protocol.call_tool(mock_utcp_client, "some_tool", {}, wrong_template)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_call_tool_file_not_found(text_protocol: TextCommunicationProtocol, mock_utcp_client: Mock):
    """Calling a tool when the file doesn't exist should raise FileNotFoundError."""
    tool_template = TextCallTemplate(name="missing", file_path="/path/that/does/not/exist.json")
    with pytest.raises(FileNotFoundError):
        await text_protocol.call_tool(mock_utcp_client, "some_tool", {}, tool_template)


@pytest.mark.asyncio
async def test_deregister_manual(text_protocol: TextCommunicationProtocol, sample_utcp_manual, mock_utcp_client: Mock):
    """Deregistering a manual should be a no-op (no errors)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_utcp_manual, f)
        temp_file = f.name

    try:
        manual_template = TextCallTemplate(name="test_manual", file_path=temp_file)
        await text_protocol.deregister_manual(mock_utcp_client, manual_template)
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_call_tool_streaming(text_protocol: TextCommunicationProtocol, sample_utcp_manual, mock_utcp_client: Mock):
    """Streaming call should yield a single chunk equal to non-streaming content."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_utcp_manual, f)
        temp_file = f.name

    try:
        tool_template = TextCallTemplate(name="tool_call", file_path=temp_file)
        # Non-streaming
        content = await text_protocol.call_tool(mock_utcp_client, "calculator", {}, tool_template)
        # Streaming
        stream = text_protocol.call_tool_streaming(mock_utcp_client, "calculator", {}, tool_template)
        chunks = [c async for c in stream]
        assert chunks == [content]
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_text_call_template_with_auth_tools():
    """Test that TextCallTemplate can be created with auth_tools."""
    auth_tools = ApiKeyAuth(api_key="test-key", var_name="Authorization", location="header")
    
    template = TextCallTemplate(
        name="test-template",
        file_path="test.json",
        auth_tools=auth_tools
    )
    
    assert template.auth_tools == auth_tools
    assert template.auth is None  # auth should still be None for file access
