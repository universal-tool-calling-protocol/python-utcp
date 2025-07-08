"""
Tests for the text file transport interface.
"""
import json
import tempfile
from pathlib import Path
import pytest
import pytest_asyncio

from utcp.client.transport_interfaces.text_transport import TextTransport
from utcp.shared.provider import TextProvider


@pytest_asyncio.fixture
async def transport() -> TextTransport:
    """Provides a clean TextTransport instance."""
    t = TextTransport()
    yield t
    await t.close()


@pytest_asyncio.fixture
def sample_utcp_manual():
    """Sample UTCP manual with multiple tools."""
    return {
        "version": "1.0.0",
        "name": "Sample Tools",
        "description": "A collection of sample tools for testing",
        "tools": [
            {
                "name": "calculator",
                "description": "Performs basic arithmetic operations",
                "inputs": {
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
                    "properties": {
                        "result": {"type": "number"}
                    }
                },
                "tags": ["math", "arithmetic"]
            },
            {
                "name": "string_utils",
                "description": "String manipulation utilities",
                "inputs": {
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
                    "properties": {
                        "result": {"type": "string"}
                    }
                },
                "tags": ["text", "utilities"]
            }
        ]
    }


@pytest_asyncio.fixture
def single_tool_definition():
    """Sample single tool definition."""
    return {
        "name": "echo",
        "description": "Echoes back the input text",
        "inputs": {
            "properties": {
                "message": {"type": "string"}
            },
            "required": ["message"]
        },
        "outputs": {
            "properties": {
                "echo": {"type": "string"}
            }
        },
        "tags": ["utility"]
    }


@pytest_asyncio.fixture
def tool_array():
    """Sample array of tool definitions."""
    return [
        {
            "name": "tool1",
            "description": "First tool",
            "inputs": {"properties": {}, "required": []},
            "outputs": {"properties": {}, "required": []},
            "tags": []
        },
        {
            "name": "tool2", 
            "description": "Second tool",
            "inputs": {"properties": {}, "required": []},
            "outputs": {"properties": {}, "required": []},
            "tags": []
        }
    ]


@pytest.mark.asyncio
async def test_register_provider_with_utcp_manual(transport: TextTransport, sample_utcp_manual):
    """Test registering a provider with a UTCP manual format file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_utcp_manual, f)
        temp_file = f.name
    
    try:
        provider = TextProvider(
            name="test_provider",
            file_path=temp_file
        )
        
        tools = await transport.register_tool_provider(provider)
        
        assert len(tools) == 2
        assert tools[0].name == "calculator"
        assert tools[0].description == "Performs basic arithmetic operations"
        assert tools[0].tags == ["math", "arithmetic"]
        
        assert tools[1].name == "string_utils"
        assert tools[1].description == "String manipulation utilities"
        assert tools[1].tags == ["text", "utilities"]
        
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_register_provider_with_single_tool(transport: TextTransport, single_tool_definition):
    """Test registering a provider with a single tool definition."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(single_tool_definition, f)
        temp_file = f.name
    
    try:
        provider = TextProvider(
            name="single_tool_provider",
            file_path=temp_file
        )
        
        tools = await transport.register_tool_provider(provider)
        
        assert len(tools) == 1
        assert tools[0].name == "echo"
        assert tools[0].description == "Echoes back the input text"
        assert tools[0].tags == ["utility"]
        
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_register_provider_with_tool_array(transport: TextTransport, tool_array):
    """Test registering a provider with an array of tool definitions."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(tool_array, f)
        temp_file = f.name
    
    try:
        provider = TextProvider(
            name="array_provider",
            file_path=temp_file
        )
        
        tools = await transport.register_tool_provider(provider)
        
        assert len(tools) == 2
        assert tools[0].name == "tool1"
        assert tools[1].name == "tool2"
        
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_register_provider_file_not_found(transport: TextTransport):
    """Test registering a provider with a non-existent file."""
    provider = TextProvider(
        name="missing_file_provider",
        file_path="/path/that/does/not/exist.json"
    )
    
    with pytest.raises(FileNotFoundError):
        await transport.register_tool_provider(provider)


@pytest.mark.asyncio
async def test_register_provider_invalid_json(transport: TextTransport):
    """Test registering a provider with invalid JSON."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{ invalid json content }")
        temp_file = f.name
    
    try:
        provider = TextProvider(
            name="invalid_json_provider",
            file_path=temp_file
        )
        
        with pytest.raises(json.JSONDecodeError):
            await transport.register_tool_provider(provider)
            
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_register_provider_invalid_format(transport: TextTransport):
    """Test registering a provider with invalid format."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"invalid": "format"}, f)
        temp_file = f.name
    
    try:
        provider = TextProvider(
            name="invalid_format_provider",
            file_path=temp_file
        )
        
        tools = await transport.register_tool_provider(provider)
        assert len(tools) == 0  # Should return empty list for invalid format
        
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_register_provider_wrong_type(transport: TextTransport):
    """Test registering a provider with wrong provider type."""
    from utcp.shared.provider import HttpProvider
    
    provider = HttpProvider(
        name="http_provider",
        url="https://example.com"
    )
    
    with pytest.raises(ValueError, match="TextTransport can only be used with TextProvider"):
        await transport.register_tool_provider(provider)


@pytest.mark.asyncio
async def test_call_tool_returns_file_content(transport: TextTransport, sample_utcp_manual):
    """Test that calling tools returns the content of the text file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_utcp_manual, f)
        temp_file = f.name
    
    try:
        provider = TextProvider(
            name="test_provider",
            file_path=temp_file
        )
        
        # Register the provider first
        await transport.register_tool_provider(provider)
        
        # Call a tool should return the file content
        content = await transport.call_tool("calculator", {"operation": "add", "a": 1, "b": 2}, provider)
        
        # Verify we get the JSON content back as a string
        assert isinstance(content, str)
        # Parse it back to verify it's the same content
        parsed_content = json.loads(content)
        assert parsed_content == sample_utcp_manual
            
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_call_tool_wrong_provider_type(transport: TextTransport):
    """Test calling a tool with wrong provider type."""
    from utcp.shared.provider import HttpProvider
    
    provider = HttpProvider(
        name="http_provider",
        url="https://example.com"
    )
    
    with pytest.raises(ValueError, match="TextTransport can only be used with TextProvider"):
        await transport.call_tool("some_tool", {}, provider)


@pytest.mark.asyncio
async def test_call_tool_file_not_found(transport: TextTransport):
    """Test calling a tool when the file doesn't exist."""
    provider = TextProvider(
        name="missing_file_provider",
        file_path="/path/that/does/not/exist.json"
    )
    
    with pytest.raises(FileNotFoundError):
        await transport.call_tool("some_tool", {}, provider)


@pytest.mark.asyncio
async def test_deregister_provider(transport: TextTransport, sample_utcp_manual):
    """Test deregistering a text provider."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_utcp_manual, f)
        temp_file = f.name
    
    try:
        provider = TextProvider(
            name="test_provider",
            file_path=temp_file
        )
        
        # Register and then deregister (should not raise any errors)
        await transport.register_tool_provider(provider)
        await transport.deregister_tool_provider(provider)
        
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_close_transport(transport: TextTransport):
    """Test closing the transport."""
    # Should not raise any errors
    await transport.close()
