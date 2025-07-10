import pytest
import aiohttp
import sys
from utcp.client.openapi_converter import OpenApiConverter
from utcp.shared.utcp_manual import UtcpManual


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
    assert sample_tool.tool_provider.provider_type == "http"
    assert sample_tool.tool_provider.http_method == "POST"
    assert "messages" in sample_tool.inputs.properties['body']['properties']
    assert "model" in sample_tool.inputs.properties['body']['properties']
    assert "choices" in sample_tool.outputs.properties
