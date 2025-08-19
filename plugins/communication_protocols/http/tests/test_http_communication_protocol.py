import pytest
import pytest_asyncio
import aiohttp
from aiohttp import web
from utcp_http.http_communication_protocol import HttpCommunicationProtocol
from utcp_http.http_call_template import HttpCallTemplate
from utcp.data.auth_implementations import ApiKeyAuth
from utcp.data.auth_implementations import BasicAuth
from utcp.data.auth_implementations import OAuth2Auth
from utcp.data.register_manual_response import RegisterManualResult
from utcp.data.call_template import CallTemplate

# Setup test HTTP server
@pytest_asyncio.fixture
async def app():
    """Create a test aiohttp application."""
    app = web.Application()
    
    # Setup routes for our test server
    async def tools_handler(request):
        # The execution call template points to the /tool endpoint
        execution_call_template = {
            "call_template_type": "http",
            "name": "test-http-call-template-executor",
            "url": str(request.url.origin()) + "/tool",
            "http_method": "GET"
        }
        # Return sample UTCP manual JSON
        utcp_manual = {
            "utcp_version": "1.0.0",
            "manual_version": "1.0.0",
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
                    "tool_call_template": execution_call_template
                }
            ]
        }
        return web.json_response(utcp_manual)
    
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
    app.router.add_get('/tool/{param1}', tool_handler)  # Add path param route
    app.router.add_post('/token', token_handler)
    app.router.add_post('/token_header_auth', token_header_auth_handler)
    app.router.add_get('/error', error_handler)
    
    return app

@pytest_asyncio.fixture
async def aiohttp_client(aiohttp_client, app):
    """Create a test client for our app."""
    return await aiohttp_client(app)


@pytest_asyncio.fixture
async def http_transport():
    """Create an HTTP communication protocol instance."""
    return HttpCommunicationProtocol()


@pytest_asyncio.fixture
async def http_call_template(aiohttp_client):
    """Create a basic HTTP call template for testing."""
    return HttpCallTemplate(
        name="test_call_template",
        url=f"http://localhost:{aiohttp_client.port}/tools",
        http_method="GET"
    )


@pytest_asyncio.fixture
async def api_key_call_template(aiohttp_client):
    """Create an HTTP call template with API key auth."""
    return HttpCallTemplate(
        name="api-key-call-template",
        url=f"http://localhost:{aiohttp_client.port}/tool",
        http_method="GET",
        auth=ApiKeyAuth(api_key="test-api-key", var_name="X-API-Key", location="header")
    )


@pytest_asyncio.fixture
async def basic_auth_call_template(aiohttp_client):
    """Create an HTTP call template with Basic auth."""
    return HttpCallTemplate(
        name="basic-auth-call-template",
        url=f"http://localhost:{aiohttp_client.port}/tool",
        http_method="GET",
        auth=BasicAuth(username="user", password="pass")
    )


@pytest_asyncio.fixture
async def oauth2_call_template(aiohttp_client):
    """Create an HTTP call template with OAuth2 auth."""
    return HttpCallTemplate(
        name="oauth2-call-template",
        url=f"http://localhost:{aiohttp_client.port}/tool",
        http_method="GET",
        auth=OAuth2Auth(
            client_id="client-id",
            client_secret="client-secret",
            token_url=f"http://localhost:{aiohttp_client.port}/token",
            scope="read write"
        )
    )

# Test register_manual
@pytest.mark.asyncio
async def test_register_manual(http_transport: HttpCommunicationProtocol, http_call_template: HttpCallTemplate):
    """Test registering a manual."""
    # Call register_manual
    result = await http_transport.register_manual(None, http_call_template)
    
    # Debug: Print the result details if it failed
    if not result.success:
        # Make a direct request to see what the server returns
        async with aiohttp.ClientSession() as session:
            async with session.get(http_call_template.url) as response:
                content = await response.text()
                print(f"Server response: {content}")
    
    # Verify the result is a RegisterManualResult
    assert isinstance(result, RegisterManualResult)
    assert result.manual is not None
    assert len(result.manual.tools) > 0, f"Expected tools but got empty list. Success: {result.success}"
    assert result.success is True
    assert not result.errors
    
    # Verify each tool has required fields
    tool = result.manual.tools[0]
    assert tool.name == "test_tool"
    assert tool.description == "Test tool"
    assert hasattr(tool, "inputs")
    assert hasattr(tool, "outputs")

# Test error handling when registering a manual
@pytest.mark.asyncio
async def test_register_manual_http_error(http_transport, aiohttp_client):
    """Test error handling when registering a manual."""
    # Create a call template that points to our error endpoint
    error_call_template = HttpCallTemplate(
        name="error-call-template",
        url=f"http://localhost:{aiohttp_client.port}/error",
        http_method="GET"
    )
    
    # Test the register method with error
    result = await http_transport.register_manual(None, error_call_template)
    
    # Verify the results
    assert isinstance(result, RegisterManualResult)
    assert result.success is False
    # On error, we should have a manual but no tools
    assert result.manual is not None
    assert len(result.manual.tools) == 0
    assert result.errors
    assert isinstance(result.errors[0], str)
    
# Test deregister_manual
@pytest.mark.asyncio
async def test_deregister_manual(http_transport, http_call_template):
    """Test deregistering a manual (should be a no-op)."""
    # Deregister should be a no-op
    await http_transport.deregister_manual(None, http_call_template)


# Test call_tool_basic
@pytest.mark.asyncio
async def test_call_tool_basic(http_transport, http_call_template, aiohttp_client):
    """Test calling a tool with basic configuration."""
    # Update call template URL to point to our /tool endpoint
    tool_call_template = HttpCallTemplate(
        name=http_call_template.name,
        url=f"http://localhost:{aiohttp_client.port}/tool",
        http_method="GET"
    )
    
    # Test calling a tool
    result = await http_transport.call_tool(None, "test_tool", {"param1": "value1"}, tool_call_template)
    
    # Verify the results
    assert result == {"result": "success"}


# Test call_tool_with_api_key
@pytest.mark.asyncio
async def test_call_tool_with_api_key(http_transport, api_key_call_template):
    """Test calling a tool with API key authentication."""
    # Test calling a tool with API key auth
    result = await http_transport.call_tool(None, "test_tool", {"param1": "value1"}, api_key_call_template)
    
    # Verify result
    assert result == {"result": "success"}
    # Note: We can't verify headers directly with the test server
    # but we know the test passes if we get a successful result


# Test call_tool_with_basic_auth
@pytest.mark.asyncio
async def test_call_tool_with_basic_auth(http_transport, basic_auth_call_template):
    """Test calling a tool with Basic authentication."""
    # Test calling a tool with Basic auth
    result = await http_transport.call_tool(None, "test_tool", {"param1": "value1"}, basic_auth_call_template)
    
    # Verify result
    assert result == {"result": "success"}


# Test call_tool_with_oauth2
@pytest.mark.asyncio
async def test_call_tool_with_oauth2(http_transport, oauth2_call_template):
    """Test calling a tool with OAuth2 authentication (credentials in body)."""
    # This test uses the primary method (credentials in body)
    result = await http_transport.call_tool(None, "test_tool", {"param1": "value1"}, oauth2_call_template)
    
    assert result == {"result": "success"}


@pytest.mark.asyncio
async def test_call_tool_with_oauth2_header_auth(http_transport, aiohttp_client):
    """Test calling a tool with OAuth2 authentication (credentials in header)."""
    # This call template points to an endpoint that expects Basic Auth for the token
    oauth2_header_call_template = HttpCallTemplate(
        name="oauth2-header-call-template",
        url=f"http://localhost:{aiohttp_client.port}/tool",
        http_method="GET",
        auth=OAuth2Auth(
            client_id="client-id",
            client_secret="client-secret",
            token_url=f"http://localhost:{aiohttp_client.port}/token_header_auth",
            scope="read write"
        )
    )

    # This test uses the fallback method (credentials in header)
    # The transport will first try the body method, which will fail against this endpoint,
    # and then it should fall back to the header method and succeed.
    result = await http_transport.call_tool(None, "test_tool", {"param1": "value1"}, oauth2_header_call_template)

    assert result == {"result": "success"}


# Test call_tool_with_body_field
@pytest.mark.asyncio
async def test_call_tool_with_body_field(http_transport, aiohttp_client):
    """Test calling a tool with a body field."""
    # Create call template with body field
    call_template = HttpCallTemplate(
        name="body-field-call-template",
        url=f"http://localhost:{aiohttp_client.port}/tool",
        http_method="POST",
        body_field="data"
    )
    
    # Test calling a tool with a body field
    result = await http_transport.call_tool(
        None,
        "test_tool",
        {"param1": "value1", "data": {"key": "value"}},
        call_template
    )
    
    # Verify result
    assert result == {"result": "success"}


# Test call_tool_with_path_params
@pytest.mark.asyncio
async def test_call_tool_with_path_params(http_transport, aiohttp_client):
    """Test calling a tool with path parameters."""
    # Create call template with path params in URL
    call_template = HttpCallTemplate(
        name="path-params-call-template",
        url=f"http://localhost:{aiohttp_client.port}/tool/{{param1}}",
        http_method="GET"
    )
    
    # Test calling a tool with path params
    result = await http_transport.call_tool(
        None,
        "test_tool",
        {"param1": "test-value", "param2": "other-value"},
        call_template
    )
    
    # Verify result
    assert result == {"result": "success"}


# Test call_tool_with_custom_headers
@pytest.mark.asyncio
async def test_call_tool_with_custom_headers(http_transport, aiohttp_client):
    """Test calling a tool with custom headers."""
    # Create call template with custom headers
    call_template = HttpCallTemplate(
        name="custom-headers-call-template",
        url=f"http://localhost:{aiohttp_client.port}/tool",
        http_method="GET",
        additional_headers={"X-Custom-Header": "custom-value"}
    )
    
    # Test calling a tool with custom headers
    result = await http_transport.call_tool(
        None,
        "test_tool",
        {"param1": "value1"},
        call_template
    )
    
    # Verify result
    assert result == {"result": "success"}


# Test call_tool_error
@pytest.mark.asyncio
async def test_call_tool_error(http_transport, aiohttp_client):
    """Test error handling when calling a tool."""
    # Create a call template that will return a DNS error (since the host doesn't exist)
    call_template = HttpCallTemplate(
        name="test-call-template",
        url="http://nonexistent.localhost:8080/404",
        http_method="GET"
    )
    
    # Test calling a tool that returns a DNS error
    with pytest.raises(Exception):
        await http_transport.call_tool(None, "test_tool", {"param1": "value1"}, call_template)
    
    # The error should be raised as an exception


# Test URL path parameters functionality
def test_build_url_with_path_params(http_transport):
    """Test the _build_url_with_path_params method with various URL patterns."""
    
    # Test 1: Simple single parameter
    arguments = {"user_id": "123", "limit": "10"}
    url = http_transport._build_url_with_path_params("https://api.example.com/users/{user_id}", arguments)
    assert url == "https://api.example.com/users/123"
    assert arguments == {"limit": "10"}  # Path parameter should be removed
    
    # Test 2: Multiple path parameters (like OpenLibrary API)
    arguments = {"key_type": "isbn", "value": "9780140328721", "format": "json"}
    url = http_transport._build_url_with_path_params("https://openlibrary.org/api/volumes/brief/{key_type}/{value}.json", arguments)
    assert url == "https://openlibrary.org/api/volumes/brief/isbn/9780140328721.json"
    assert arguments == {"format": "json"}  # Path parameters should be removed
    
    # Test 3: Complex URL with multiple parameters
    arguments = {"user_id": "123", "post_id": "456", "comment_id": "789", "limit": "10", "offset": "0"}
    url = http_transport._build_url_with_path_params("https://api.example.com/users/{user_id}/posts/{post_id}/comments/{comment_id}", arguments)
    assert url == "https://api.example.com/users/123/posts/456/comments/789"
    assert arguments == {"limit": "10", "offset": "0"}  # Path parameters should be removed
    
    # Test 4: URL with no path parameters
    arguments = {"param1": "value1", "param2": "value2"}
    url = http_transport._build_url_with_path_params("https://api.example.com/endpoint", arguments)
    assert url == "https://api.example.com/endpoint"
    assert arguments == {"param1": "value1", "param2": "value2"}  # Arguments should remain unchanged
    
    # Test 5: Error case - missing parameter
    arguments = {"user_id": "123"}
    with pytest.raises(ValueError, match="Missing required path parameter: post_id"):
        http_transport._build_url_with_path_params("https://api.example.com/users/{user_id}/posts/{post_id}", arguments)
    
    # Test 6: Error case - unreplaced parameters (this should not happen in practice as the first missing parameter will raise)
    # The actual implementation will raise on the first missing parameter encountered
    arguments = {"user_id": "123"}
    with pytest.raises(ValueError, match="Missing required path parameter: post_id"):
        http_transport._build_url_with_path_params("https://api.example.com/users/{user_id}/posts/{post_id}", arguments)


@pytest.mark.asyncio
async def test_call_tool_with_path_parameters(http_transport):
    """Test calling a tool with URL path parameters."""

    # Create a test server that handles path parameters
    app = web.Application()

    async def path_param_handler(request):
        # Extract path parameters from the URL
        user_id = request.match_info.get('user_id')
        post_id = request.match_info.get('post_id')
        
        # Also get query parameters
        limit = request.query.get('limit', '10')
        
        return web.json_response({
            "user_id": user_id,
            "post_id": post_id,
            "limit": limit,
            "message": f"Retrieved post {post_id} for user {user_id} with limit {limit}"
        })
    
    app.router.add_get('/users/{user_id}/posts/{post_id}', path_param_handler)

    # Create our own test client for this specific test
    from aiohttp.test_utils import TestServer, TestClient
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        base_url = f"http://localhost:{client.port}"
    
        # Create a call template with path parameters in the URL
        call_template = HttpCallTemplate(
            name="test_call_template",
            url=f"{base_url}/users/{{user_id}}/posts/{{post_id}}",
            http_method="GET"
        )
        
        # Call the tool with path parameters
        result = await http_transport.call_tool(
            None,
            "get_user_post",
            {"user_id": "123", "post_id": "456", "limit": "20"},
            call_template
        )
        
        # Verify the result
        assert result["user_id"] == "123"
        assert result["post_id"] == "456"
        assert result["limit"] == "20"
        assert "Retrieved post 456 for user 123 with limit 20" in result["message"]

    finally:
        # Clean up the test client
        await client.close()

# Streaming tests: call_tool_streaming should yield a single element equal to call_tool result


@pytest.mark.asyncio
async def test_call_tool_streaming_basic(http_transport, http_call_template, aiohttp_client):
    """Streaming basic call should yield one result identical to call_tool."""
    tool_call_template = HttpCallTemplate(
        name=http_call_template.name,
        url=f"http://localhost:{aiohttp_client.port}/tool",
        http_method="GET",
    )
    stream = http_transport.call_tool_streaming(None, "test_tool", {"param1": "value1"}, tool_call_template)
    results = [chunk async for chunk in stream]
    assert results == [{"result": "success"}]


@pytest.mark.asyncio
async def test_call_tool_streaming_with_api_key(http_transport, api_key_call_template):
    """Streaming with API key auth yields one aggregated result."""
    stream = http_transport.call_tool_streaming(None, "test_tool", {"param1": "value1"}, api_key_call_template)
    results = [chunk async for chunk in stream]
    assert results == [{"result": "success"}]


@pytest.mark.asyncio
async def test_call_tool_streaming_with_basic_auth(http_transport, basic_auth_call_template):
    """Streaming with Basic auth yields one aggregated result."""
    stream = http_transport.call_tool_streaming(None, "test_tool", {"param1": "value1"}, basic_auth_call_template)
    results = [chunk async for chunk in stream]
    assert results == [{"result": "success"}]


@pytest.mark.asyncio
async def test_call_tool_streaming_with_oauth2(http_transport, oauth2_call_template):
    """Streaming with OAuth2 (credentials in body) yields one aggregated result."""
    stream = http_transport.call_tool_streaming(None, "test_tool", {"param1": "value1"}, oauth2_call_template)
    results = [chunk async for chunk in stream]
    assert results == [{"result": "success"}]


@pytest.mark.asyncio
async def test_call_tool_streaming_with_oauth2_header_auth(http_transport, aiohttp_client):
    """Streaming with OAuth2 (credentials in header) yields one aggregated result."""
    oauth2_header_call_template = HttpCallTemplate(
        name="oauth2-header-call-template",
        url=f"http://localhost:{aiohttp_client.port}/tool",
        http_method="GET",
        auth=OAuth2Auth(
            client_id="client-id",
            client_secret="client-secret",
            token_url=f"http://localhost:{aiohttp_client.port}/token_header_auth",
            scope="read write",
        ),
    )
    stream = http_transport.call_tool_streaming(None, "test_tool", {"param1": "value1"}, oauth2_header_call_template)
    results = [chunk async for chunk in stream]
    assert results == [{"result": "success"}]


@pytest.mark.asyncio
async def test_call_tool_streaming_with_body_field(http_transport, aiohttp_client):
    """Streaming POST with body_field yields one aggregated result."""
    call_template = HttpCallTemplate(
        name="body-field-call-template",
        url=f"http://localhost:{aiohttp_client.port}/tool",
        http_method="POST",
        body_field="data",
    )
    stream = http_transport.call_tool_streaming(
        None,
        "test_tool",
        {"param1": "value1", "data": {"key": "value"}},
        call_template,
    )
    results = [chunk async for chunk in stream]
    assert results == [{"result": "success"}]


@pytest.mark.asyncio
async def test_call_tool_streaming_with_path_params(http_transport, aiohttp_client):
    """Streaming with URL path params yields one aggregated result."""
    call_template = HttpCallTemplate(
        name="path-params-call-template",
        url=f"http://localhost:{aiohttp_client.port}/tool/{{param1}}",
        http_method="GET",
    )
    stream = http_transport.call_tool_streaming(
        None,
        "test_tool",
        {"param1": "test-value", "param2": "other-value"},
        call_template,
    )
    results = [chunk async for chunk in stream]
    assert results == [{"result": "success"}]


@pytest.mark.asyncio
async def test_call_tool_streaming_with_custom_headers(http_transport, aiohttp_client):
    """Streaming with additional headers yields one aggregated result."""
    call_template = HttpCallTemplate(
        name="custom-headers-call-template",
        url=f"http://localhost:{aiohttp_client.port}/tool",
        http_method="GET",
        additional_headers={"X-Custom-Header": "custom-value"},
    )
    stream = http_transport.call_tool_streaming(
        None,
        "test_tool",
        {"param1": "value1"},
        call_template,
    )
    results = [chunk async for chunk in stream]
    assert results == [{"result": "success"}]


@pytest.mark.asyncio
async def test_call_tool_streaming_error(http_transport):
    """Streaming should propagate errors from call_tool (no elements yielded)."""
    call_template = HttpCallTemplate(
        name="test-call-template",
        url="http://nonexistent.localhost:8080/404",
        http_method="GET",
    )
    with pytest.raises(Exception):
        async for _ in http_transport.call_tool_streaming(None, "test_tool", {"param1": "value1"}, call_template):
            pass


@pytest.mark.asyncio
async def test_call_tool_missing_path_parameter(http_transport):
    """Test error handling when path parameters are missing."""
    
    # Create a call template with path parameters
    call_template = HttpCallTemplate(
        name="test_call_template",
        url="https://api.example.com/users/{user_id}/posts/{post_id}",
        http_method="GET"
    )
    
    # Try to call the tool without required path parameters
    with pytest.raises(ValueError, match="Missing required path parameter: post_id"):
        await http_transport.call_tool(
            None,
            "test_tool",
            {"user_id": "123"},  # Missing post_id
            call_template
        )


@pytest.mark.asyncio
async def test_call_tool_openlibrary_style_url(http_transport):
    """Test calling a tool with OpenLibrary-style URL path parameters."""
    
    # Create a call template with OpenLibrary-style URL (the original problem case)
    call_template = HttpCallTemplate(
        name="openlibrary_call_template",
        url="https://openlibrary.org/api/volumes/brief/{key_type}/{value}.json",
        http_method="GET"
    )
    
    # Test the URL building (we can't make actual requests to OpenLibrary in tests)
    arguments = {"key_type": "isbn", "value": "9780140328721", "format": "json"}
    url = http_transport._build_url_with_path_params(call_template.url, arguments.copy())
    
    # Verify the URL was built correctly
    assert url == "https://openlibrary.org/api/volumes/brief/isbn/9780140328721.json"
    
    # Verify that path parameters were removed from arguments, leaving only query parameters
    expected_remaining = {"format": "json"}
    http_transport._build_url_with_path_params(call_template.url, arguments)
    assert arguments == expected_remaining
