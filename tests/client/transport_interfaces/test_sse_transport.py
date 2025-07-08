import pytest
import pytest_asyncio
import json
import asyncio
import base64
from unittest.mock import MagicMock, patch, AsyncMock

import aiohttp
from aiohttp import web

from utcp.client.transport_interfaces.sse_transport import SSEClientTransport
from utcp.shared.provider import SSEProvider
from utcp.shared.auth import ApiKeyAuth, BasicAuth, OAuth2Auth

# --- Test Data ---

SAMPLE_TOOLS_JSON = {
    "tools": [
        {
            "name": "test_tool",
            "description": "Test tool",
            "inputs": {
                "type": "object",
                "properties": {"param1": {"type": "string"}}
            },
            "outputs": {
                "type": "object",
                "properties": {"result": {"type": "string"}}
            },
            "tags": []
        }
    ]
}

SAMPLE_SSE_EVENTS = [
    'id: 1\ndata: {"message": "First part"}\n\n',
    'id: 2\nevent: data\ndata: { "message": "Second part" }\n\n',
    'id: 3\nevent: complete\ndata: { "message": "End of stream" }\n\n'
]

# --- Test Server Handlers ---

async def tools_handler(request):
    return web.json_response(SAMPLE_TOOLS_JSON)

async def sse_handler(request):
    # Check auth
    if 'X-API-Key' in request.headers and request.headers['X-API-Key'] != 'test-api-key':
        return web.Response(status=401, text="Invalid API Key")
    if 'Authorization' in request.headers:
        auth_header = request.headers['Authorization']
        if auth_header.startswith('Basic'):
            # Basic dXNlcjpwYXNz
            if auth_header != f"Basic {base64.b64encode(b'user:pass').decode()}":
                return web.Response(status=401, text="Invalid Basic Auth")
        elif auth_header.startswith('Bearer'):
            if auth_header not in ('Bearer test-access-token', 'Bearer test-access-token-header'):
                return web.Response(status=401, text="Invalid Bearer Token")

    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={'Content-Type': 'text/event-stream'}
    )
    await response.prepare(request)

    for event in SAMPLE_SSE_EVENTS:
        await response.write(event.encode('utf-8'))
        await asyncio.sleep(0.01) # Simulate network delay
    
    return response

async def token_handler(request):
    # OAuth2 token endpoint (credentials in body)
    data = await request.post()
    if data.get('client_id') == 'client-id' and data.get('client_secret') == 'client-secret':
        return web.json_response({
            "access_token": "test-access-token",
            "token_type": "Bearer",
            "expires_in": 3600
        })
    return web.json_response({"error": "invalid_client"}, status=401)

async def token_header_auth_handler(request):
    # OAuth2 token endpoint (credentials in header)
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Basic '):
        return web.json_response({"error": "missing_auth"}, status=401)
    
    return web.json_response({
        "access_token": "test-access-token-header",
        "token_type": "Bearer",
        "expires_in": 3600
    })

async def error_handler(request):
    return web.Response(status=500, text="Internal Server Error")

# --- Pytest Fixtures ---

@pytest.fixture
def logger():
    return MagicMock()

@pytest_asyncio.fixture
async def sse_transport(logger):
    """Fixture to create and properly tear down an SSEClientTransport instance."""
    transport = SSEClientTransport(logger=logger)
    yield transport
    await transport.close()

@pytest.fixture
def app():
    application = web.Application()
    application.router.add_get("/tools", tools_handler)
    application.router.add_get("/events", sse_handler)
    application.router.add_post("/events", sse_handler)
    application.router.add_post("/token", token_handler)
    application.router.add_post("/token_header_auth", token_header_auth_handler)
    application.router.add_get("/error", error_handler)
    return application

import pytest_asyncio

@pytest_asyncio.fixture
async def oauth2_provider(aiohttp_client, app):
    client = await aiohttp_client(app)
    return SSEProvider(
        name="oauth2-provider",
        url=f"{client.make_url('/events')}",
        auth=OAuth2Auth(
            client_id="client-id",
            client_secret="client-secret",
            token_url=f"{client.make_url('/token')}"
        )
    )

# --- Tests ---

@pytest.mark.asyncio
async def test_register_tool_provider(sse_transport, aiohttp_client, app):
    """Test registering a tool provider."""
    client = await aiohttp_client(app)
    provider = SSEProvider(name="test", url=f"{client.make_url('/tools')}")
    tools = await sse_transport.register_tool_provider(provider)
    assert len(tools) == 1
    assert tools[0].name == "test_tool"

@pytest.mark.asyncio
async def test_register_tool_provider_error(sse_transport, aiohttp_client, app, logger):
    """Test error handling when registering a tool provider."""
    client = await aiohttp_client(app)
    provider = SSEProvider(name="test-error", url=f"{client.make_url('/error')}")
    tools = await sse_transport.register_tool_provider(provider)
    assert tools == []
    # The actual exception message can vary, so we check that the log message starts with the expected text.
    assert logger.call_count == 1
    call_args, call_kwargs = logger.call_args
    assert call_args[0].startswith(f"Error discovering tools from '{provider.name}':")
    assert call_kwargs == {'error': True}

@pytest.mark.asyncio
async def test_call_tool_basic(sse_transport, aiohttp_client, app):
    """Test calling a tool with basic configuration."""
    client = await aiohttp_client(app)
    provider = SSEProvider(name="test-basic", url=f"{client.make_url('/events')}")
    
    stream_iterator = await sse_transport.call_tool("test_tool", {"param1": "value1"}, provider)
    
    results = []
    async for event in stream_iterator:
        results.append(event)
    
    assert len(results) == 3
    assert results[0] == {"message": "First part"}
    assert results[1] == {"message": "Second part"}

@pytest.mark.asyncio
async def test_call_tool_with_api_key(sse_transport, aiohttp_client, app):
    """Test calling a tool with API key authentication."""
    client = await aiohttp_client(app)
    provider = SSEProvider(
        name="api-key-provider",
        url=f"{client.make_url('/events')}",
        auth=ApiKeyAuth(var_name="X-API-Key", api_key="test-api-key")
    )
    stream_iterator = await sse_transport.call_tool("test_tool", {}, provider)
    results = [event async for event in stream_iterator]
    assert len(results) == 3

@pytest.mark.asyncio
async def test_call_tool_with_basic_auth(sse_transport, aiohttp_client, app):
    """Test calling a tool with Basic authentication."""
    client = await aiohttp_client(app)
    provider = SSEProvider(
        name="basic-auth-provider",
        url=f"{client.make_url('/events')}",
        auth=BasicAuth(username="user", password="pass")
    )
    stream_iterator = await sse_transport.call_tool("test_tool", {}, provider)
    results = [event async for event in stream_iterator]
    assert len(results) == 3

@pytest.mark.asyncio
async def test_call_tool_with_oauth2(sse_transport, oauth2_provider, app):
    """Test calling a tool with OAuth2 authentication (credentials in body)."""
    # The provider fixture is already configured with the correct client URL
    events = []
    async for event in await sse_transport.call_tool("test_tool", {"param1": "value1"}, oauth2_provider):
        events.append(event)
    
    assert len(events) == 3
    assert events[0] == {"message": "First part"}
    assert events[1] == {"message": "Second part"}
    assert events[2] == {"message": "End of stream"}

@pytest.mark.asyncio
async def test_call_tool_with_oauth2_header_auth(sse_transport, aiohttp_client, app):
    """Test calling a tool with OAuth2 authentication (credentials in header)."""
    client = await aiohttp_client(app)
    oauth2_header_provider = SSEProvider(
        name="oauth2-header-provider",
        url=f"{client.make_url('/events')}",
        auth=OAuth2Auth(
            client_id="client-id",
            client_secret="client-secret",
            token_url=f"{client.make_url('/token_header_auth')}",
            scope="read write"
        )
    )

    events = []
    async for event in await sse_transport.call_tool("test_tool", {"param1": "value1"}, oauth2_header_provider):
        events.append(event)

    assert len(events) == 3
    assert events[0] == {"message": "First part"}
    assert events[1] == {"message": "Second part"}
    assert events[2] == {"message": "End of stream"}

@pytest.mark.asyncio
async def test_call_tool_with_body_field(sse_transport, aiohttp_client, app):
    """Test calling a tool with a body field."""
    client = await aiohttp_client(app)
    provider = SSEProvider(
        name="body-field-provider",
        url=f"{client.make_url('/events')}",
        body_field="data",
        headers={"Content-Type": "application/json"}
    )
    stream_iterator = await sse_transport.call_tool(
        "test_tool", 
        {"param1": "value1", "data": {"key": "value"}}, 
        provider
    )
    results = [event async for event in stream_iterator]
    assert len(results) == 3

@pytest.mark.asyncio
async def test_call_tool_error(sse_transport, aiohttp_client, app, logger):
    """Test error handling when calling a tool."""
    client = await aiohttp_client(app)
    provider = SSEProvider(name="test-error", url=f"{client.make_url('/error')}")
    with pytest.raises(aiohttp.ClientResponseError) as excinfo:
        await sse_transport.call_tool("test_tool", {}, provider)
    
    assert excinfo.value.status == 500
    logger.assert_called_with(f"Error establishing SSE connection to '{provider.name}': 500, message='Internal Server Error', url='{provider.url}'", error=True)

@pytest.mark.asyncio
async def test_deregister_tool_provider(sse_transport, aiohttp_client, app):
    """Test deregistering a tool provider closes the connection."""
    client = await aiohttp_client(app)
    provider = SSEProvider(name="test-deregister", url=f"{client.make_url('/events')}")
    
    # Make a call to establish a connection
    stream_iterator = await sse_transport.call_tool("test_tool", {}, provider)
    assert provider.name in sse_transport._active_connections
    response, session = sse_transport._active_connections[provider.name]
    
    # Consume one item to ensure connection is active
    await anext(stream_iterator)
    
    # Deregister
    await sse_transport.deregister_tool_provider(provider)
    
    # Verify connection and session are closed and removed
    assert provider.name not in sse_transport._active_connections
    assert response.closed
    assert session.closed
