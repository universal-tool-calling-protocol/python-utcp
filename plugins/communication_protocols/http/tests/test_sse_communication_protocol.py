import pytest
import pytest_asyncio
import json
import asyncio
import base64
from unittest.mock import MagicMock, patch, AsyncMock

import aiohttp
from aiohttp import web

from utcp_http.sse_communication_protocol import SseCommunicationProtocol
from utcp_http.sse_call_template import SseCallTemplate
from utcp.data.auth_implementations import ApiKeyAuth, BasicAuth, OAuth2Auth
from utcp.data.register_manual_response import RegisterManualResult

# --- Test Data ---

SAMPLE_SSE_EVENTS = [
    'id: 1\ndata: {"message": "First part"}\n\n',
    'id: 2\nevent: data\ndata: { "message": "Second part" }\n\n',
    'id: 3\nevent: complete\ndata: { "message": "End of stream" }\n\n'
]

# --- Test Server Handlers ---

async def tools_handler(request):
    execution_call_template = {
        "call_template_type": "sse",
        "name": "test-sse-call-template-executor",
        "url": str(request.url.origin()) + "/events",
        "http_method": "GET",
        "content_type": "application/json"
    }
    utcp_manual = {
        "utcp_version": "1.0.0",
        "manual_version": "1.0.0",
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
                "tags": [],
                "tool_call_template": execution_call_template
            }
        ]
    }
    return web.json_response(utcp_manual)

async def events_handler(request):
    if request.method not in ('GET', 'POST'):
        return web.Response(status=405)

    # Check auth
    if 'X-API-Key' in request.headers and request.headers['X-API-Key'] != 'test-api-key':
        return web.Response(status=401, text="Invalid API Key")
    if 'Authorization' in request.headers:
        auth_header = request.headers['Authorization']
        if auth_header.startswith('Basic'):
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
    data = await request.post()
    if data.get('client_id') == 'client-id' and data.get('client_secret') == 'client-secret':
        return web.json_response({
            "access_token": "test-access-token",
            "token_type": "Bearer",
            "expires_in": 3600
        })
    return web.json_response({"error": "invalid_client"}, status=401)

async def token_header_auth_handler(request):
    auth_header = request.headers.get('Authorization')
    if auth_header == f"Basic {base64.b64encode(b'client-id:client-secret').decode()}":
        return web.json_response({
            "access_token": "test-access-token-header",
            "token_type": "Bearer",
            "expires_in": 3600
        })
    return web.json_response({"error": "invalid_client"}, status=401)

async def error_handler(request):
    return web.Response(status=500, text="Internal Server Error")

# --- Pytest Fixtures ---

@pytest_asyncio.fixture
async def sse_transport():
    """Fixture to create and properly tear down an SseCommunicationProtocol instance."""
    transport = SseCommunicationProtocol()
    yield transport
    await transport.close()

@pytest.fixture
def app():
    app = web.Application()
    app.router.add_get("/tools", tools_handler)
    app.router.add_route('*', '/events', events_handler)
    app.router.add_post("/token", token_handler)
    app.router.add_post("/token_header_auth", token_header_auth_handler)
    app.router.add_get("/error", error_handler)
    return app

@pytest_asyncio.fixture
async def oauth2_call_template(aiohttp_client, app):
    client = await aiohttp_client(app)
    return SseCallTemplate(
        name="oauth2-call-template",
        url=f"{client.make_url('/events')}",
        auth=OAuth2Auth(
            client_id="client-id",
            client_secret="client-secret",
            token_url=f"{client.make_url('/token')}",
            scope="read write"
        )
    )

# --- Tests ---

@pytest.mark.asyncio
async def test_register_manual(sse_transport, aiohttp_client, app):
    """Test registering a manual."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(name="test-call-template", url=f"{client.make_url('/tools')}")
    result = await sse_transport.register_manual(None, call_template)
    
    assert isinstance(result, RegisterManualResult)
    assert result.success
    assert not result.errors
    assert result.manual is not None
    assert len(result.manual.tools) == 1
    assert result.manual.tools[0].name == "test_tool"

@pytest.mark.asyncio
async def test_register_manual_error(sse_transport, aiohttp_client, app):
    """Test error handling when registering a manual."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(name="test-error", url=f"{client.make_url('/error')}")
    result = await sse_transport.register_manual(None, call_template)
    assert not result.success
    assert result.manual is not None
    assert len(result.manual.tools) == 0
    assert result.errors
    assert isinstance(result.errors[0], str)

@pytest.mark.asyncio
async def test_call_tool_basic(sse_transport, aiohttp_client, app):
    """Test calling a tool with basic configuration."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(name="test-basic", url=f"{client.make_url('/events')}")

    events = []
    async for event in sse_transport.call_tool_streaming(None, "test_tool", {"param1": "value1"}, call_template):
        events.append(event)
    
    assert len(events) == 3
    assert events[0] == {"message": "First part"}
    assert events[1] == {"message": "Second part"}
    assert events[2] == {"message": "End of stream"}

@pytest.mark.asyncio
async def test_call_tool_with_api_key(sse_transport, aiohttp_client, app):
    """Test calling a tool with API key authentication."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(
        name="api-key-call-template",
        url=f"{client.make_url('/events')}",
        auth=ApiKeyAuth(api_key="test-api-key", header_name="X-API-Key")
    )
    stream_iterator = sse_transport.call_tool_streaming(None, "test_tool", {}, call_template)
    results = [event async for event in stream_iterator]
    assert len(results) == 3

@pytest.mark.asyncio
async def test_call_tool_with_basic_auth(sse_transport, aiohttp_client, app):
    """Test calling a tool with Basic authentication."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(
        name="basic-auth-call-template",
        url=f"{client.make_url('/events')}",
        auth=BasicAuth(username="user", password="pass")
    )
    stream_iterator = sse_transport.call_tool_streaming(None, "test_tool", {}, call_template)
    results = [event async for event in stream_iterator]
    assert len(results) == 3

@pytest.mark.asyncio
async def test_call_tool_with_oauth2(sse_transport, oauth2_call_template, app):
    """Test calling a tool with OAuth2 authentication (credentials in body)."""
    events = []
    async for event in sse_transport.call_tool_streaming(None, "test_tool", {"param1": "value1"}, oauth2_call_template):
        events.append(event)
    
    assert len(events) == 3
    assert events[0] == {"message": "First part"}
    assert events[1] == {"message": "Second part"}
    assert events[2] == {"message": "End of stream"}

@pytest.mark.asyncio
async def test_call_tool_with_oauth2_header_auth(sse_transport, aiohttp_client, app):
    """Test calling a tool with OAuth2 authentication (credentials in header)."""
    client = await aiohttp_client(app)
    oauth2_header_call_template = SseCallTemplate(
        name="oauth2-header-call-template",
        url=f"{client.make_url('/events')}",
        auth=OAuth2Auth(
            client_id="client-id",
            client_secret="client-secret",
            token_url=f"{client.make_url('/token_header_auth')}",
            scope="read write"
        )
    )

    events = []
    async for event in sse_transport.call_tool_streaming(None, "test_tool", {"param1": "value1"}, oauth2_header_call_template):
        events.append(event)

    assert len(events) == 3
    assert events[0] == {"message": "First part"}
    assert events[1] == {"message": "Second part"}
    assert events[2] == {"message": "End of stream"}

@pytest.mark.asyncio
async def test_call_tool_with_body_field(sse_transport, aiohttp_client, app):
    """Test calling a tool with a body field."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(
        name="body-field-call-template",
        url=f"{client.make_url('/events')}",
        body_field="data",
        headers={"Content-Type": "application/json"}
    )
    stream_iterator = sse_transport.call_tool_streaming(
        None,
        "test_tool",
        {"param1": "value1", "data": {"key": "value"}},
        call_template
    )
    results = [event async for event in stream_iterator]
    assert len(results) == 3

@pytest.mark.asyncio
async def test_call_tool_error(sse_transport, aiohttp_client, app):
    """Test error handling when calling a tool."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(name="test-error", url=f"{client.make_url('/error')}")
    with pytest.raises(aiohttp.ClientResponseError) as excinfo:
        async for _ in sse_transport.call_tool_streaming(None, "test_tool", {}, call_template):
            pass
    
    assert excinfo.value.status == 500

@pytest.mark.asyncio
async def test_deregister_manual(sse_transport, aiohttp_client, app):
    """Test deregistering a manual closes the connection."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(name="test-deregister", url=f"{client.make_url('/events')}")
    
    # Make a call to establish a connection
    stream_iterator = sse_transport.call_tool_streaming(None, "test_tool", {}, call_template)
    await anext(stream_iterator)
    assert call_template.name in sse_transport._active_connections
    response, session = sse_transport._active_connections[call_template.name]

    # Deregister
    await sse_transport.deregister_manual(None, call_template)
    
    # Verify connection and session are closed and removed
    assert call_template.name not in sse_transport._active_connections
    assert response.closed
    assert session.closed

@pytest.mark.asyncio
async def test_call_tool_basic_nonstream(sse_transport, aiohttp_client, app):
    """Non-streaming call should aggregate SSE events into a list (basic)."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(name="test-basic", url=f"{client.make_url('/events')}")

    result = await sse_transport.call_tool(None, "test_tool", {"param1": "value1"}, call_template)

    assert isinstance(result, list)
    assert len(result) == 3
    assert result[0] == {"message": "First part"}
    assert result[1] == {"message": "Second part"}
    assert result[2] == {"message": "End of stream"}

@pytest.mark.asyncio
async def test_call_tool_with_api_key_nonstream(sse_transport, aiohttp_client, app):
    """Non-streaming call with API key should behave like streaming."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(
        name="api-key-call-template",
        url=f"{client.make_url('/events')}",
        auth=ApiKeyAuth(api_key="test-api-key", header_name="X-API-Key")
    )

    result = await sse_transport.call_tool(None, "test_tool", {}, call_template)
    
    assert isinstance(result, list)
    assert len(result) == 3

@pytest.mark.asyncio
async def test_call_tool_with_basic_auth_nonstream(sse_transport, aiohttp_client, app):
    """Non-streaming call with Basic auth should behave like streaming."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(
        name="basic-auth-call-template",
        url=f"{client.make_url('/events')}",
        auth=BasicAuth(username="user", password="pass")
    )

    result = await sse_transport.call_tool(None, "test_tool", {}, call_template)
    
    assert isinstance(result, list)
    assert len(result) == 3

@pytest.mark.asyncio
async def test_call_tool_with_oauth2_nonstream(sse_transport, oauth2_call_template, app):
    """Non-streaming call with OAuth2 (body credentials) should aggregate events."""
    result = await sse_transport.call_tool(None, "test_tool", {"param1": "value1"}, oauth2_call_template)
    assert isinstance(result, list)
    assert len(result) == 3
    assert result[0] == {"message": "First part"}
    assert result[1] == {"message": "Second part"}
    assert result[2] == {"message": "End of stream"}

@pytest.mark.asyncio
async def test_call_tool_with_oauth2_header_auth_nonstream(sse_transport, aiohttp_client, app):
    """Non-streaming call with OAuth2 (header credentials) should aggregate events."""
    client = await aiohttp_client(app)
    oauth2_header_call_template = SseCallTemplate(
        name="oauth2-header-call-template",
        url=f"{client.make_url('/events')}",
        auth=OAuth2Auth(
            client_id="client-id",
            client_secret="client-secret",
            token_url=f"{client.make_url('/token_header_auth')}",
            scope="read write"
        )
    )

    result = await sse_transport.call_tool(None, "test_tool", {"param1": "value1"}, oauth2_header_call_template)

    assert isinstance(result, list)
    assert len(result) == 3
    assert result[0] == {"message": "First part"}
    assert result[1] == {"message": "Second part"}
    assert result[2] == {"message": "End of stream"}

@pytest.mark.asyncio
async def test_call_tool_with_body_field_nonstream(sse_transport, aiohttp_client, app):
    """Non-streaming call with body field should aggregate events."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(
        name="body-field-call-template",
        url=f"{client.make_url('/events')}",
        body_field="data",
        headers={"Content-Type": "application/json"}
    )

    result = await sse_transport.call_tool(
        None,
        "test_tool",
        {"param1": "value1", "data": {"key": "value"}},
        call_template
    )
    assert isinstance(result, list)
    assert len(result) == 3

@pytest.mark.asyncio
async def test_call_tool_error_nonstream(sse_transport, aiohttp_client, app):
    """Non-streaming call should raise same error on server failure."""
    client = await aiohttp_client(app)
    call_template = SseCallTemplate(name="test-error", url=f"{client.make_url('/error')}")
    with pytest.raises(aiohttp.ClientResponseError) as excinfo:
        await sse_transport.call_tool(None, "test_tool", {}, call_template)
    assert excinfo.value.status == 500
