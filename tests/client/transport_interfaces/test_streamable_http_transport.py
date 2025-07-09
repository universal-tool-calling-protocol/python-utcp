import pytest
import pytest_asyncio
import json
import asyncio
from unittest.mock import MagicMock

from aiohttp import web

from utcp.client.transport_interfaces.streamable_http_transport import StreamableHttpClientTransport
from utcp.shared.provider import StreamableHttpProvider
from utcp.shared.auth import ApiKeyAuth, BasicAuth, OAuth2Auth

# --- Test Data ---

SAMPLE_TOOLS_JSON = {
    "version": "1.0",
    "tools": [
        {
            "name": "test_tool",
            "description": "Test tool",
            "inputs": {},
            "outputs": {},
            "tags": [],
            "provider": {
                "provider_type": "http_stream",
                "name": "test-streamable-http-provider-executor",
                "url": "http://test-url/tool",
                "http_method": "GET",
                "content_type": "application/json"
            }
        }
    ]
}

SAMPLE_NDJSON_RESPONSE = [
    {'status': 'running', 'progress': 0},
    {'status': 'running', 'progress': 50},
    {'status': 'completed', 'result': 'done'}
]

# --- Fixtures ---

@pytest.fixture
def logger():
    """Fixture for a mock logger."""
    return MagicMock()

@pytest_asyncio.fixture
async def streamable_http_transport(logger):
    """Fixture to create and properly tear down a StreamableHttpClientTransport instance."""
    transport = StreamableHttpClientTransport(logger=logger)
    yield transport
    await transport.close()

@pytest.fixture
def app():
    """Fixture for the aiohttp test application."""
    async def discover(request):
        execution_provider = {
            "provider_type": "http_stream",
            "name": "test-streamable-http-provider-executor",
            "url": str(request.url.origin()) + "/stream-ndjson",
            "http_method": "GET",
            "content_type": "application/x-ndjson"
        }
        utcp_manual = {
            "version": "1.0",
            "tools": [
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "inputs": {},
                    "outputs": {},
                    "tags": [],
                    "provider": execution_provider
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
            await asyncio.sleep(0.01) # Simulate network delay
        await response.write_eof()
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
        await response.write_eof()
        return response

    async def check_api_key_auth(request):
        if request.headers.get("X-API-Key") != "test-key":
            return web.Response(status=401, text="Unauthorized: Invalid API Key")
        return await stream_ndjson(request)

    async def check_basic_auth(request):
        auth_header = request.headers.get('Authorization')
        if not auth_header or 'Basic dXNlcjpwYXNz' not in auth_header: # user:pass
            return web.Response(status=401, text="Unauthorized: Invalid Basic Auth")
        return await stream_ndjson(request)

    async def oauth_token_handler(request):
        data = await request.post()
        if data.get('client_id') == 'test-client' and data.get('client_secret') == 'test-secret':
            return web.json_response({'access_token': 'token-from-body', 'token_type': 'Bearer'})
        return web.Response(status=401, text="Invalid client credentials")

    async def oauth_token_header_handler(request):
        auth_header = request.headers.get('Authorization')
        if auth_header and 'Basic dGVzdC1jbGllbnQ6dGVzdC1zZWNyZXQ=' in auth_header: # test-client:test-secret
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
async def test_register_tool_provider(streamable_http_transport, aiohttp_client, app):
    """Test successful tool provider registration."""
    client = await aiohttp_client(app)
    provider = StreamableHttpProvider(name="test-provider", url=f"{client.make_url('/discover')}")
    tools = await streamable_http_transport.register_tool_provider(provider)
    assert len(tools) == 1
    assert tools[0].name == "test_tool"

@pytest.mark.asyncio
async def test_register_tool_provider_error(streamable_http_transport, aiohttp_client, app, logger):
    """Test error handling during tool provider registration."""
    client = await aiohttp_client(app)
    provider = StreamableHttpProvider(name="test-provider", url=f"{client.make_url('/error')}")
    tools = await streamable_http_transport.register_tool_provider(provider)
    assert tools == []
    assert logger.call_count > 0
    log_message = logger.call_args[0][0]
    assert "Error discovering tools" in log_message

@pytest.mark.asyncio
async def test_call_tool_ndjson_stream(streamable_http_transport, aiohttp_client, app):
    """Test calling a tool that returns an NDJSON stream."""
    client = await aiohttp_client(app)
    provider = StreamableHttpProvider(name="ndjson-provider", url=f"{client.make_url('/stream-ndjson')}", content_type='application/x-ndjson')
    
    stream_iterator = await streamable_http_transport.call_tool("test_tool", {}, provider)
    
    results = [item async for item in stream_iterator]
    
    assert results == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_binary_stream(streamable_http_transport, aiohttp_client, app):
    """Test calling a tool that returns a binary stream."""
    client = await aiohttp_client(app)
    provider = StreamableHttpProvider(name="binary-provider", url=f"{client.make_url('/stream-binary')}", content_type='application/octet-stream', chunk_size=6)

    stream_iterator = await streamable_http_transport.call_tool("test_tool", {}, provider)

    results = [chunk async for chunk in stream_iterator]

    assert results == [b'chunk1', b'chunk2']

@pytest.mark.asyncio
async def test_call_tool_with_api_key(streamable_http_transport, aiohttp_client, app):
    """Test that the API key is correctly sent in the headers."""
    client = await aiohttp_client(app)
    auth = ApiKeyAuth(var_name="X-API-Key", api_key="test-key")
    provider = StreamableHttpProvider(name="auth-provider", url=f"{client.make_url('/auth-api-key')}", auth=auth, content_type='application/x-ndjson')

    stream_iterator = await streamable_http_transport.call_tool("test_tool", {}, provider)
    results = [item async for item in stream_iterator]
    
    assert results == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_with_basic_auth(streamable_http_transport, aiohttp_client, app):
    """Test streaming with Basic authentication."""
    client = await aiohttp_client(app)
    auth = BasicAuth(username="user", password="pass")
    provider = StreamableHttpProvider(name="basic-auth-provider", url=f"{client.make_url('/auth-basic')}", auth=auth, content_type='application/x-ndjson')

    stream_iterator = await streamable_http_transport.call_tool("test_tool", {}, provider)
    results = [item async for item in stream_iterator]
    
    assert results == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_with_oauth2_body(streamable_http_transport, aiohttp_client, app):
    """Test streaming with OAuth2 (credentials in body)."""
    client = await aiohttp_client(app)
    auth = OAuth2Auth(client_id="test-client", client_secret="test-secret", token_url=f"{client.make_url('/token')}")
    provider = StreamableHttpProvider(name="oauth-provider", url=f"{client.make_url('/auth-oauth')}", auth=auth, content_type='application/x-ndjson')

    stream_iterator = await streamable_http_transport.call_tool("test_tool", {}, provider)
    results = [item async for item in stream_iterator]
    
    assert results == SAMPLE_NDJSON_RESPONSE

@pytest.mark.asyncio
async def test_call_tool_with_oauth2_header_fallback(streamable_http_transport, aiohttp_client, app):
    """Test streaming with OAuth2 (fallback to Basic Auth header)."""
    client = await aiohttp_client(app)
    # This token endpoint will fail for the body method, forcing a fallback.
    auth = OAuth2Auth(client_id="test-client", client_secret="test-secret", token_url=f"{client.make_url('/token-header')}")
    provider = StreamableHttpProvider(name="oauth-fallback-provider", url=f"{client.make_url('/auth-oauth')}", auth=auth, content_type='application/x-ndjson')

    stream_iterator = await streamable_http_transport.call_tool("test_tool", {}, provider)
    results = [item async for item in stream_iterator]
    
    assert results == SAMPLE_NDJSON_RESPONSE
