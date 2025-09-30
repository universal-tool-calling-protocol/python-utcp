import pytest
import aiohttp
import sys
from utcp_http.openapi_converter import OpenApiConverter
from utcp.data.utcp_manual import UtcpManual
from utcp.data.auth_implementations.api_key_auth import ApiKeyAuth


@pytest.mark.asyncio
async def test_openai_spec_conversion():
    """Tests that the OpenAI OpenAPI spec can be successfully converted into a UTCPManual."""
    url = "https://api.apis.guru/v2/specs/openai.com/1.2.0/openapi.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            openapi_spec = await response.json()

    converter = OpenApiConverter(openapi_spec, spec_url=url)
    utcp_manual = converter.convert()

    assert isinstance(utcp_manual, UtcpManual)
    assert len(utcp_manual.tools) > 0

    # Check a few things on a sample tool to ensure parsing is reasonable
    sample_tool = next((tool for tool in utcp_manual.tools if tool.name == "createChatCompletion"), None)
    assert sample_tool is not None
    assert sample_tool.tool_call_template.call_template_type == "http"
    assert sample_tool.tool_call_template.http_method == "POST"
    body_schema = sample_tool.inputs.properties.get('body')
    assert body_schema is not None


@pytest.mark.asyncio
async def test_openapi_converter_with_auth_tools():
    """Test OpenAPI converter with auth_tools parameter."""
    url = "https://api.apis.guru/v2/specs/openai.com/1.2.0/openapi.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            openapi_spec = await response.json()

    # Test with auth_tools parameter
    auth_tools = ApiKeyAuth(
        api_key="Bearer test-token",
        var_name="Authorization", 
        location="header"
    )
    
    converter = OpenApiConverter(openapi_spec, spec_url=url, auth_tools=auth_tools)
    utcp_manual = converter.convert()

    assert isinstance(utcp_manual, UtcpManual)
    assert len(utcp_manual.tools) > 0
    
    # Verify auth_tools is stored
    assert converter.auth_tools == auth_tools
