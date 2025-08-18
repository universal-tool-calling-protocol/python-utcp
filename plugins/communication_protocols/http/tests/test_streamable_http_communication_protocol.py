import pytest
import pytest_asyncio
import json
import asyncio
import aiohttp
from aiohttp import web

from utcp_http.streamable_http_communication_protocol import StreamableHttpCommunicationProtocol
from utcp_http.streamable_http_call_template import StreamableHttpCallTemplate
from utcp.data.auth_implementations import ApiKeyAuth, BasicAuth, OAuth2Auth
from utcp.data.register_manual_response import RegisterManualResult

# --- Test Data ---

SAMPLE_NDJSON_RESPONSE = [
    {'status': 'running', 'progress': 0},
    {'status': 'running', 'progress': 50},
    {'status': 'completed', 'result': 'done'}
]

# --- Fixtures ---

@pytest_asyncio.fixture
async def streamable_http_transport():
    """Fixture to create and properly tear down a StreamableHttpCommunicationProtocol instance."""
    transport = StreamableHttpCommunicationProtocol()
    yield transport
    await transport.close()

@pytest.fixture
def app():
    """Fixture for the aiohttp test application."""
    async def discover(request):
        execution_call_template = {
            "call_template_type": "streamable_http",
            "name": "test-streamable-http-executor",
            "url": str(request.url.origin()) + "/stream-ndjson",
            "http_method": "GET",
            "content_type": "application/x-ndjson"
        }
        utcp_manual = {
            "utcp_version": "1.0.0",
            "manual_version": "1.0.0",
            "tools": [
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "inputs": {},
                    "outputs": {},
                    "tags": [],
                    "tool_call_template": execution_call_template
                }
            ]
        }
        return web.json_response(utcp_manual)

    async def stream_ndjson(request):
        response = web.StreamResponse(
            status=200,
            reason='OK',
            headers={'Content-Type': 'application/x-ndjson'}
        )
        await response.prepare(request)
        for item in SAMPLE_NDJSON_RESPONSE:
            await response.write(json.dumps(item).encode('utf-8') + b'\n')
            await asyncio.sleep(0.01)  # Simulate network delay
        return response

    async def stream_binary(request):
        response = web.StreamResponse(
            status=200,
            reason='OK',
            headers={'Content-Type': 'application/octet-stream'}
        )
        await response.prepare(request)
        await response.write(b'chunk1')
        await response.write(b'chunk2')
        return response

    async def check_api_key_auth(request):
        if request.headers.get("X-API-Key") != "test-key":
            return web.Response(status=401, text="Unauthorized: Invalid API Key")
        return await stream_ndjson(request)

    async def check_basic_auth(request):
        auth_header = request.headers.get('Authorization')
        if not auth_header or 'Basic dXNlcjpwYXNz' not in auth_header:  # user:pass
            return web.Response(status=401, text="Unauthorized: Invalid Basic Auth")
        return await stream_ndjson(request)

    async def oauth_token_handler(request):
        data = await request.post()
        if data.get('client_id') == 'test-client' and data.get('client_secret') == 'test-secret':
            return web.json_response({'access_token': 'token-from-body', 'token_type': 'Bearer'})
        return web.Response(status=401, text="Invalid client credentials")

    async def oauth_token_header_handler(request):
        auth_header = request.headers.get('Authorization')
        if auth_header and 'Basic dGVzdC1jbGllbnQ6dGVzdC1zZWNyZXQ=' in auth_header:  # test-client:test-secret
            return web.json_response({'access_token': 'token-from-header', 'token_type': 'Bearer'})
        return web.Response(status=401, text="Invalid client credentials via header")

    async def check_oauth(request):
        auth_header = request.headers.get('Authorization')
        if auth_header in ('Bearer token-from-body', 'Bearer token-from-header'):
            return await stream_ndjson(request)
        return web.Response(status=401, text="Unauthorized: Invalid OAuth Token")

    async def error_endpoint(request):
        return web.Response(status=500, text="Internal Server Error")

    app = web.Application()
    app.add_routes([
        web.get('/discover', discover),
        web.get('/stream-ndjson', stream_ndjson),
        web.get('/stream-binary', stream_binary),
        web.get('/auth-api-key', check_api_key_auth),
        web.get('/auth-basic', check_basic_auth),
        web.get('/auth-oauth', check_oauth),
        web.post('/token', oauth_token_handler),
        web.post('/token-header', oauth_token_header_handler),
        web.get('/error', error_endpoint),
    ])
    return app

# --- Test Cases ---

@pytest.mark.asyncio
async def test_register_manual(streamable_http_transport, aiohttp_client, app):
    """Test successful manual registration."""
    client = await aiohttp_client(app)
    call_template = StreamableHttpCallTemplate(name="test-provider", url=f"{client.make_url('/discover')}")
    result = await streamable_http_transport.register_manual(None, call_template)
    
    assert isinstance(result, RegisterManualResult)
    assert result.success
    assert not result.errors
    assert result.manual is not None
    assert len(result.manual.tools) == 1
    assert result.manual.tools[0].name == "test_tool"

@pytest.mark.asyncio
async def test_register_manual_error(streamable_http_transport, aiohttp_client, app):
    """Test error handling during manual registration."""
    client = await aiohttp_client(app)
    call_template = StreamableHttpCallTemplate(name="test-provider", url=f"{client.make_url('/error')}")
    result = await streamable_http_transport.register_manual(None, call_template)
    
    assert isinstance(result, RegisterManualResult)
    assert not result.success
    assert result.errors
    assert isinstance(result.errors[0], str)
    assert result.manual is not None
    assert len(result.manual.tools) == 0

@pytest.mark.asyncio
async def test_call_tool_streaming_ndjson(streamable_http_transport, aiohttp_client, app):
    """Test calling a tool that returns an NDJSON stream."""
    client = await aiohttp_client(app)
    call_template = StreamableHttpCallTemplate(name="ndjson-provider", url=f"{client.make_url('/stream-ndjson')}", content_type='application/x-ndjson')
    
    stream_iterator = streamable_http_transport.call_tool_streaming(
        None, "test_tool", {}, call_template
    )
    
    results = [item async for item in stream_iterator]
    
    assert results == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_binary_stream(streamable_http_transport, aiohttp_client, app):
    """Test calling a tool that returns a binary stream."""
    client = await aiohttp_client(app)
    call_template = StreamableHttpCallTemplate(
        name="binary-provider",
        url=f"{client.make_url('/stream-binary')}",
        content_type='application/octet-stream',
        chunk_size=6
    )

    stream_iterator = streamable_http_transport.call_tool_streaming(None, "test_tool", {}, call_template)

    results = [chunk async for chunk in stream_iterator]

    assert results == [b'chunk1', b'chunk2']

@pytest.mark.asyncio
async def test_call_tool_with_api_key(streamable_http_transport, aiohttp_client, app):
    """Test that the API key is correctly sent in the headers."""
    client = await aiohttp_client(app)
    auth = ApiKeyAuth(var_name="X-API-Key", api_key="test-key", location="header")
    call_template = StreamableHttpCallTemplate(
        name="auth-provider",
        url=f"{client.make_url('/auth-api-key')}",
        auth=auth,
        content_type='application/x-ndjson'
    )

    stream_iterator = streamable_http_transport.call_tool_streaming(None, "test_tool", {}, call_template)
    results = [item async for item in stream_iterator]
    
    assert results == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_with_basic_auth(streamable_http_transport, aiohttp_client, app):
    """Test streaming with Basic authentication."""
    client = await aiohttp_client(app)
    auth = BasicAuth(username="user", password="pass")
    call_template = StreamableHttpCallTemplate(
        name="basic-auth-provider",
        url=f"{client.make_url('/auth-basic')}",
        auth=auth,
        content_type='application/x-ndjson'
    )

    stream_iterator = streamable_http_transport.call_tool_streaming(None, "test_tool", {}, call_template)
    results = [item async for item in stream_iterator]
    
    assert results == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_with_oauth2_body(streamable_http_transport, aiohttp_client, app):
    """Test streaming with OAuth2 (credentials in body)."""
    client = await aiohttp_client(app)
    auth = OAuth2Auth(client_id="test-client", client_secret="test-secret", token_url=f"{client.make_url('/token')}")
    call_template = StreamableHttpCallTemplate(
        name="oauth-provider",
        url=f"{client.make_url('/auth-oauth')}",
        auth=auth,
        content_type='application/x-ndjson'
    )

    stream_iterator = streamable_http_transport.call_tool_streaming(None, "test_tool", {}, call_template)
    results = [item async for item in stream_iterator]
    
    assert results == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_with_oauth2_header_fallback(streamable_http_transport, aiohttp_client, app):
    """Test streaming with OAuth2 (fallback to Basic Auth header)."""
    client = await aiohttp_client(app)
    # This token endpoint will fail for the body method, forcing a fallback.
    auth = OAuth2Auth(client_id="test-client", client_secret="test-secret", token_url=f"{client.make_url('/token-header')}")
    call_template = StreamableHttpCallTemplate(
        name="oauth-fallback-provider",
        url=f"{client.make_url('/auth-oauth')}",
        auth=auth,
        content_type='application/x-ndjson'
    )

    stream_iterator = streamable_http_transport.call_tool_streaming(None, "test_tool", {}, call_template)
    results = [item async for item in stream_iterator]
    
    assert results == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_ndjson(streamable_http_transport, aiohttp_client, app):
    """Non-streaming call should return full list for NDJSON."""
    client = await aiohttp_client(app)
    call_template = StreamableHttpCallTemplate(name="ndjson-provider", url=f"{client.make_url('/stream-ndjson')}", content_type='application/x-ndjson')

    result = await streamable_http_transport.call_tool(None, "test_tool", {}, call_template)

    assert result == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_binary(streamable_http_transport, aiohttp_client, app):
    """Non-streaming call should return concatenated bytes for binary stream."""
    client = await aiohttp_client(app)
    call_template = StreamableHttpCallTemplate(
        name="binary-provider",
        url=f"{client.make_url('/stream-binary')}",
        content_type='application/octet-stream',
        chunk_size=6
    )

    result = await streamable_http_transport.call_tool(None, "test_tool", {}, call_template)

    assert result == b'chunk1chunk2'

@pytest.mark.asyncio
async def test_call_tool_with_api_key_nonstream(streamable_http_transport, aiohttp_client, app):
    """Non-streaming call with API key in header should behave like streaming."""
    client = await aiohttp_client(app)
    auth = ApiKeyAuth(var_name="X-API-Key", api_key="test-key", location="header")
    call_template = StreamableHttpCallTemplate(
        name="auth-provider",
        url=f"{client.make_url('/auth-api-key')}",
        auth=auth,
        content_type='application/x-ndjson'
    )

    result = await streamable_http_transport.call_tool(None, "test_tool", {}, call_template)
    
    assert result == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_with_basic_auth_nonstream(streamable_http_transport, aiohttp_client, app):
    """Non-streaming call with Basic auth should behave like streaming."""
    client = await aiohttp_client(app)
    auth = BasicAuth(username="user", password="pass")
    call_template = StreamableHttpCallTemplate(
        name="basic-auth-provider",
        url=f"{client.make_url('/auth-basic')}",
        auth=auth,
        content_type='application/x-ndjson'
    )

    result = await streamable_http_transport.call_tool(None, "test_tool", {}, call_template)
    
    assert result == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_with_oauth2_body_nonstream(streamable_http_transport, aiohttp_client, app):
    """Non-streaming call with OAuth2 (credentials in body) should behave like streaming."""
    client = await aiohttp_client(app)
    auth = OAuth2Auth(client_id="test-client", client_secret="test-secret", token_url=f"{client.make_url('/token')}")
    call_template = StreamableHttpCallTemplate(
        name="oauth-provider",
        url=f"{client.make_url('/auth-oauth')}",
        auth=auth,
        content_type='application/x-ndjson'
    )

    result = await streamable_http_transport.call_tool(None, "test_tool", {}, call_template)
    
    assert result == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_with_oauth2_header_fallback_nonstream(streamable_http_transport, aiohttp_client, app):
    """Non-streaming call with OAuth2 (fallback to Basic Auth header) should behave like streaming."""
    client = await aiohttp_client(app)
    auth = OAuth2Auth(client_id="test-client", client_secret="test-secret", token_url=f"{client.make_url('/token-header')}")
    call_template = StreamableHttpCallTemplate(
        name="oauth-fallback-provider",
        url=f"{client.make_url('/auth-oauth')}",
        auth=auth,
        content_type='application/x-ndjson'
    )

    result = await streamable_http_transport.call_tool(None, "test_tool", {}, call_template)
    
    assert result == SAMPLE_NDJSON_RESPONSE
