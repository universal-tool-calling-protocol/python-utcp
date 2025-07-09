import pytest
import pytest_asyncio
import json
import aiohttp
from aiohttp import web
from unittest.mock import MagicMock

from utcp.client.transport_interfaces.http_transport import HttpClientTransport
from utcp.shared.provider import HttpProvider
from utcp.shared.auth import ApiKeyAuth, BasicAuth, OAuth2Auth


# Setup test HTTP server
@pytest_asyncio.fixture
async def app():
    """Create a test aiohttp application."""
    app = web.Application()
    
    # Setup routes for our test server
    async def tools_handler(request):
        # The execution provider points to the /tool endpoint
        execution_provider = {
            "provider_type": "http",
            "name": "test-http-provider-executor",
            "url": str(request.url.origin()) + "/tool",
            "http_method": "GET",
            "content_type": "application/json"
        }
        # Return sample tools JSON
        return web.json_response({
            "version": "1.0",
            "tools": [
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "inputs": {
                        "type": "object",
                        "properties": {
                            "param1": {"type": "string"}
                        }
                    },
                    "outputs": {
                        "type": "object",
                        "properties": {
                            "result": {"type": "string"}
                        }
                    },
                    "tags": [],
                    "provider": execution_provider
                }
            ]
        })
    
    async def token_handler(request):
        # OAuth2 token endpoint (credentials in body)
        data = await request.post()
        if data.get('client_id') == 'client-id' and data.get('client_secret') == 'client-secret':
            return web.json_response({
                "access_token": "test-access-token",
                "token_type": "Bearer",
                "expires_in": 3600
            })
        return web.json_response({
            "error": "invalid_client",
            "error_description": "Invalid client credentials"
        }, status=401)

    async def token_header_auth_handler(request):
        # OAuth2 token endpoint (credentials in header)
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Basic '):
            return web.json_response({"error": "missing_auth"}, status=401)
        
        # Dummy check for credentials
        # In a real scenario, you'd decode and verify
        return web.json_response({
            "access_token": "test-access-token-header",
            "token_type": "Bearer",
            "expires_in": 3600
        })
    
    async def tool_handler(request):
        # Check for Authorization header
        auth_header = request.headers.get('Authorization')
        
        # Handle OAuth2 Bearer token
        if auth_header and auth_header.startswith('Bearer ') and 'test-access-token' not in auth_header:
            raise web.HTTPUnauthorized(text="Invalid OAuth token")
        
        # Handle Basic Auth
        elif auth_header and auth_header.startswith('Basic '):
            # In a real server we would decode and verify the credentials
            # For test purposes, we'll just accept any Basic auth header
            pass
        
        # Check for API Key header
        api_key_header = request.headers.get('X-API-Key')
        if api_key_header is not None and api_key_header != 'test-api-key':
            raise web.HTTPUnauthorized(text="Invalid API key")
            
        # Return tool response
        return web.json_response({"result": "success"})
    
    async def discover_handler(request):
        tools_data = [
            {
                "name": "test_tool",
                "description": "Test tool",
                "inputs": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string"}
                    }
                },
                "outputs": {
                    "type": "object",
                    "properties": {
                        "result": {"type": "string"}
                    }
                },
                "tags": []
            }
        ]
        utcp_manual = {
            "version": "1.0",
            "tools": tools_data
        }
        return web.json_response(utcp_manual)
    
    async def error_handler(request):
        # Simulate an error response
        raise web.HTTPNotFound(text="Not found")
    
    app.router.add_get('/tools', tools_handler)
    app.router.add_get('/tool', tool_handler)
    app.router.add_post('/tool', tool_handler)
    app.router.add_post('/token', token_handler)
    app.router.add_post('/token_header_auth', token_header_auth_handler)
    app.router.add_get('/error', error_handler)
    
    return app

@pytest_asyncio.fixture
async def aiohttp_client(aiohttp_client, app):
    """Create a test client for our app."""
    return await aiohttp_client(app)


@pytest.fixture
def logger():
    """Create a mock logger."""
    return MagicMock()


@pytest.fixture
def http_transport(logger):
    """Create an HTTP transport instance."""
    return HttpClientTransport(logger=logger)


@pytest_asyncio.fixture
async def http_provider(aiohttp_client):
    """Create a basic HTTP provider for testing."""
    return HttpProvider(
        name="test-http-provider",
        url=f"{aiohttp_client.make_url('/tools')}",
        http_method="GET",
        content_type="application/json"
    )


@pytest_asyncio.fixture
async def api_key_provider(aiohttp_client):
    """Create an HTTP provider with API key auth."""
    return HttpProvider(
        name="api-key-provider",
        url=f"{aiohttp_client.make_url('/tool')}",
        http_method="GET",
        content_type="application/json",
        auth=ApiKeyAuth(var_name="X-API-Key", api_key="test-api-key")
    )


@pytest_asyncio.fixture
async def basic_auth_provider(aiohttp_client):
    """Create an HTTP provider with Basic auth."""
    return HttpProvider(
        name="basic-auth-provider",
        url=f"{aiohttp_client.make_url('/tool')}",
        http_method="GET",
        content_type="application/json",
        auth=BasicAuth(username="user", password="pass")
    )


@pytest_asyncio.fixture
async def oauth2_provider(aiohttp_client):
    """Create an HTTP provider with OAuth2 auth."""
    return HttpProvider(
        name="oauth2-provider",
        url=f"{aiohttp_client.make_url('/tool')}",
        http_method="GET",
        content_type="application/json",
        auth=OAuth2Auth(
            client_id="client-id",
            client_secret="client-secret",
            token_url=f"{aiohttp_client.make_url('/token')}",
            scope="read write"
        )
    )

# Test register_tool_provider
@pytest.mark.asyncio
async def test_register_tool_provider(http_transport, http_provider, logger):
    """Test registering a tool provider."""
    # Call register_tool_provider
    tools = await http_transport.register_tool_provider(http_provider)
    
    # Verify the result is a list of tools
    assert isinstance(tools, list)
    assert len(tools) > 0
    
    # Verify each tool has required fields
    tool = tools[0]
    assert tool.name == "test_tool"
    assert tool.description == "Test tool"
    assert hasattr(tool, "inputs")
    assert hasattr(tool, "outputs")

# Test error handling when registering a tool provider
@pytest.mark.asyncio
async def test_register_tool_provider_http_error(http_transport, logger, aiohttp_client):
    """Test error handling when registering a tool provider."""
    # Create a provider that points to our error endpoint
    error_provider = HttpProvider(
        name="error-provider",
        url=f"{aiohttp_client.make_url('/error')}",
        http_method="GET",
        content_type="application/json"
    )
    
    # Test the register method with error
    tools = await http_transport.register_tool_provider(error_provider)
    
    # Verify the results
    assert tools == []
    # Logger should be called with error
    logger.assert_called()
    
# Test deregister_tool_provider
@pytest.mark.asyncio
async def test_deregister_tool_provider(http_transport, http_provider):
    """Test deregistering a tool provider (should be a no-op)."""
    # Deregister should be a no-op
    await http_transport.deregister_tool_provider(http_provider)


# Test call_tool_basic
@pytest.mark.asyncio
async def test_call_tool_basic(http_transport, http_provider, aiohttp_client):
    """Test calling a tool with basic configuration."""
    # Update provider URL to point to our /tool endpoint
    tool_provider = HttpProvider(
        name=http_provider.name,
        url=f"{aiohttp_client.make_url('/tool')}",
        http_method="GET",
        content_type=http_provider.content_type
    )
    
    # Test calling a tool
    result = await http_transport.call_tool("test_tool", {"param1": "value1"}, tool_provider)
    
    # Verify the results
    assert result == {"result": "success"}


# Test call_tool_with_api_key
@pytest.mark.asyncio
async def test_call_tool_with_api_key(http_transport, api_key_provider):
    """Test calling a tool with API key authentication."""
    # Test calling a tool with API key auth
    result = await http_transport.call_tool("test_tool", {"param1": "value1"}, api_key_provider)
    
    # Verify result
    assert result == {"result": "success"}
    # Note: We can't verify headers directly with the test server
    # but we know the test passes if we get a successful result


# Test call_tool_with_basic_auth
@pytest.mark.asyncio
async def test_call_tool_with_basic_auth(http_transport, basic_auth_provider):
    """Test calling a tool with Basic authentication."""
    # Test calling a tool with Basic auth
    result = await http_transport.call_tool("test_tool", {"param1": "value1"}, basic_auth_provider)
    
    # Verify result
    assert result == {"result": "success"}


# Test call_tool_with_oauth2
@pytest.mark.asyncio
async def test_call_tool_with_oauth2(http_transport, oauth2_provider):
    """Test calling a tool with OAuth2 authentication (credentials in body)."""
    # This test uses the primary method (credentials in body)
    result = await http_transport.call_tool("test_tool", {"param1": "value1"}, oauth2_provider)
    
    assert result == {"result": "success"}


@pytest.mark.asyncio
async def test_call_tool_with_oauth2_header_auth(http_transport, aiohttp_client):
    """Test calling a tool with OAuth2 authentication (credentials in header)."""
    # This provider points to an endpoint that expects Basic Auth for the token
    oauth2_header_provider = HttpProvider(
        name="oauth2-header-provider",
        url=f"{aiohttp_client.make_url('/tool')}",
        http_method="GET",
        content_type="application/json",
        auth=OAuth2Auth(
            client_id="client-id",
            client_secret="client-secret",
            token_url=f"{aiohttp_client.make_url('/token_header_auth')}",
            scope="read write"
        )
    )

    # This test uses the fallback method (credentials in header)
    # The transport will first try the body method, which will fail against this endpoint,
    # and then it should fall back to the header method and succeed.
    result = await http_transport.call_tool("test_tool", {"param1": "value1"}, oauth2_header_provider)

    assert result == {"result": "success"}


# Test call_tool_with_body_field
@pytest.mark.asyncio
async def test_call_tool_with_body_field(http_transport, aiohttp_client):
    """Test calling a tool with a body field."""
    # Create provider with body field
    provider = HttpProvider(
        name="body-field-provider",
        url=f"{aiohttp_client.make_url('/tool')}",
        http_method="POST",
        content_type="application/json",
        body_field="data"
    )
    
    # Test calling a tool with a body field
    result = await http_transport.call_tool(
        "test_tool",
        {"param1": "value1", "data": {"key": "value"}},
        provider
    )
    
    # Verify result
    assert result == {"result": "success"}


# Test call_tool_with_header_fields
@pytest.mark.asyncio
async def test_call_tool_with_header_fields(http_transport, aiohttp_client):
    """Test calling a tool with header fields."""
    # Create provider with header fields
    provider = HttpProvider(
        name="header-fields-provider",
        url=f"{aiohttp_client.make_url('/tool')}",
        http_method="GET",
        content_type="application/json",
        header_fields=["X-Custom-Header"]
    )
    
    # Test calling a tool with a header field
    result = await http_transport.call_tool(
        "test_tool",
        {"param1": "value1", "X-Custom-Header": "custom-value"},
        provider
    )
    
    # Verify result
    assert result == {"result": "success"}


# Test call_tool_error
@pytest.mark.asyncio
async def test_call_tool_error(http_transport, logger, aiohttp_client):
    """Test error handling when calling a tool."""
    # Create a provider that points to our error endpoint
    error_provider = HttpProvider(
        name="error-provider",
        url=f"{aiohttp_client.make_url('/error')}",
        http_method="GET",
        content_type="application/json"
    )
    
    # Test calling a tool with error
    with pytest.raises(aiohttp.ClientResponseError):
        await http_transport.call_tool("test_tool", {"param1": "value1"}, error_provider)
    
    # Verify the logger was called
    logger.assert_called()
