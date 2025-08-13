import pytest
import aiohttp
from utcp_http.openapi_converter import OpenApiConverter
from utcp.data.utcp_manual import UtcpManual
from utcp.data.auth_implementations import ApiKeyAuth
from utcp_http.http_call_template import HttpCallTemplate


@pytest.mark.asyncio
async def test_webscraping_ai_spec_conversion():
    """Tests that the WebScraping.AI OpenAPI spec can be successfully converted into a UTCPManual."""
    url = "https://api.apis.guru/v2/specs/webscraping.ai/2.0.7/openapi.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            openapi_spec = await response.json()

    converter = OpenApiConverter(openapi_spec, spec_url=url)
    utcp_manual = converter.convert()

    assert isinstance(utcp_manual, UtcpManual)
    assert len(utcp_manual.tools) == 4  # account, getHTML, getSelected, getSelectedMultiple

    # Check that all tools use HTTP call templates
    for tool in utcp_manual.tools:
        assert isinstance(tool.tool_call_template, HttpCallTemplate)
        assert tool.tool_call_template.type == "http"
        assert tool.tool_call_template.http_method == "GET"


@pytest.mark.asyncio
async def test_webscraping_ai_auth_extraction():
    """Tests that API key authentication is correctly extracted from the WebScraping.AI spec."""
    url = "https://api.apis.guru/v2/specs/webscraping.ai/2.0.7/openapi.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            openapi_spec = await response.json()

    converter = OpenApiConverter(openapi_spec, spec_url=url)
    utcp_manual = converter.convert()

    # All tools should have API key authentication
    for tool in utcp_manual.tools:
        assert tool.tool_call_template.auth is not None
        assert isinstance(tool.tool_call_template.auth, ApiKeyAuth)
        assert tool.tool_call_template.auth.var_name == "api_key"
        assert tool.tool_call_template.auth.api_key.startswith("${API_KEY_")
        assert tool.tool_call_template.auth.location == "query"


@pytest.mark.asyncio
async def test_webscraping_ai_specific_tools():
    """Tests specific tools and their properties from the WebScraping.AI spec."""
    url = "https://api.apis.guru/v2/specs/webscraping.ai/2.0.7/openapi.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            openapi_spec = await response.json()

    converter = OpenApiConverter(openapi_spec, spec_url=url)
    utcp_manual = converter.convert()

    # Test account tool
    account_tool = next((tool for tool in utcp_manual.tools if tool.name == "account"), None)
    assert account_tool is not None
    assert account_tool.description == "Information about your account calls quota"
    assert account_tool.tool_call_template.url == "https://api.webscraping.ai/account"
    assert "Account" in account_tool.tags

    # Test getHTML tool
    html_tool = next((tool for tool in utcp_manual.tools if tool.name == "getHTML"), None)
    assert html_tool is not None
    assert html_tool.description == "Page HTML by URL"
    assert html_tool.tool_call_template.url == "https://api.webscraping.ai/html"
    assert "HTML" in html_tool.tags
    
    # Check that URL parameter is required
    assert "url" in html_tool.inputs.properties
    assert html_tool.inputs.required is not None
    assert "url" in html_tool.inputs.required

    # Test getSelected tool
    selected_tool = next((tool for tool in utcp_manual.tools if tool.name == "getSelected"), None)
    assert selected_tool is not None
    assert selected_tool.tool_call_template.url == "https://api.webscraping.ai/selected"
    assert "selector" in selected_tool.inputs.properties
    assert "url" in selected_tool.inputs.properties

    # Test getSelectedMultiple tool
    selected_multiple_tool = next((tool for tool in utcp_manual.tools if tool.name == "getSelectedMultiple"), None)
    assert selected_multiple_tool is not None
    assert selected_multiple_tool.tool_call_template.url == "https://api.webscraping.ai/selected-multiple"
    assert "selectors" in selected_multiple_tool.inputs.properties
    assert selected_multiple_tool.inputs.properties["selectors"].type == "array"


@pytest.mark.asyncio
async def test_webscraping_ai_parameter_resolution():
    """Tests that parameter references are correctly resolved in the WebScraping.AI spec."""
    url = "https://api.apis.guru/v2/specs/webscraping.ai/2.0.7/openapi.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            openapi_spec = await response.json()

    converter = OpenApiConverter(openapi_spec, spec_url=url)
    utcp_manual = converter.convert()

    # Test that parameters with $ref are resolved
    html_tool = next((tool for tool in utcp_manual.tools if tool.name == "getHTML"), None)
    assert html_tool is not None
    
    # Check that referenced parameters are properly resolved
    assert "url" in html_tool.inputs.properties
    url_schema = html_tool.inputs.properties.get("url")
    assert url_schema is not None
    assert url_schema.description == "URL of the target page"
    assert url_schema.type == "string"

    assert "timeout" in html_tool.inputs.properties
    timeout_schema = html_tool.inputs.properties.get("timeout")
    assert timeout_schema is not None
    assert isinstance(timeout_schema.description, str) and timeout_schema.description.startswith("Maximum processing time in ms")
    assert timeout_schema.type == "integer"
    assert timeout_schema.default == 10000

    assert "js" in html_tool.inputs.properties
    js_schema = html_tool.inputs.properties.get("js")
    assert js_schema is not None
    assert js_schema.type == "boolean"
    assert js_schema.default is True


@pytest.mark.asyncio
async def test_webscraping_ai_response_schemas():
    """Tests that response schemas are correctly extracted from the WebScraping.AI spec."""
    url = "https://api.apis.guru/v2/specs/webscraping.ai/2.0.7/openapi.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            openapi_spec = await response.json()

    converter = OpenApiConverter(openapi_spec, spec_url=url)
    utcp_manual = converter.convert()

    # Test account tool output schema
    account_tool = next((tool for tool in utcp_manual.tools if tool.name == "account"), None)
    assert account_tool is not None
    assert account_tool.outputs.type == "object"
    assert "remaining_api_calls" in account_tool.outputs.properties
    assert "remaining_concurrency" in account_tool.outputs.properties
    assert "resets_at" in account_tool.outputs.properties

    # Test getHTML tool output schema (should be string for HTML)
    html_tool = next((tool for tool in utcp_manual.tools if tool.name == "getHTML"), None)
    assert html_tool is not None
    assert html_tool.outputs.type == "string"

    # Test getSelectedMultiple tool output schema (should be array)
    selected_multiple_tool = next((tool for tool in utcp_manual.tools if tool.name == "getSelectedMultiple"), None)
    assert selected_multiple_tool is not None
    assert selected_multiple_tool.outputs.type == "array"
    # Now we can check array item types with our enhanced schema
    assert selected_multiple_tool.outputs.items is not None
    assert selected_multiple_tool.outputs.items.type == "string"
