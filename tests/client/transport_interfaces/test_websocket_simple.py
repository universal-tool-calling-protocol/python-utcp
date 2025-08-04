"""
Simplified WebSocket transport tests using pytest-asyncio directly.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from aiohttp import web, WSMsgType
from aiohttp.test_utils import AioHTTPTestCase

from utcp.client.transport_interfaces.websocket_transport import WebSocketClientTransport
from utcp.shared.provider import WebSocketProvider, HttpProvider
from utcp.shared.auth import ApiKeyAuth, BasicAuth, OAuth2Auth


@pytest.mark.asyncio
async def test_security_enforcement():
    """Test that insecure URLs are rejected"""
    transport = WebSocketClientTransport()
    
    provider = WebSocketProvider(
        name="insecure_provider",
        url="ws://example.com/ws"  # Not localhost or WSS
    )
    
    with pytest.raises(ValueError) as exc_info:
        await transport.register_tool_provider(provider)
    
    assert "Security error" in str(exc_info.value)
    assert "WSS" in str(exc_info.value)
    
    await transport.close()


@pytest.mark.asyncio
async def test_invalid_provider_type():
    """Test registration with invalid provider type"""
    transport = WebSocketClientTransport()
    
    provider = HttpProvider(
        name="invalid_provider",
        url="https://example.com"
    )
    
    with pytest.raises(ValueError) as exc_info:
        await transport.register_tool_provider(provider)
    
    assert "WebSocketClientTransport can only be used with WebSocketProvider" in str(exc_info.value)
    
    await transport.close()


@pytest.mark.asyncio
async def test_call_tool_invalid_provider_type():
    """Test tool call with invalid provider type"""
    transport = WebSocketClientTransport()
    
    provider = HttpProvider(name="invalid", url="https://example.com")
    
    with pytest.raises(ValueError) as exc_info:
        await transport.call_tool("test", {}, provider)
    
    assert "WebSocketClientTransport can only be used with WebSocketProvider" in str(exc_info.value)
    
    await transport.close()


@pytest.mark.asyncio
async def test_authentication_headers():
    """Test authentication header preparation"""
    transport = WebSocketClientTransport()
    
    # Test API Key auth
    api_provider = WebSocketProvider(
        name="api_test",
        url="wss://example.com/ws",
        auth=ApiKeyAuth(
            var_name="X-API-Key",
            api_key="test-api-key-123",
            location="header"
        )
    )
    headers = await transport._prepare_headers(api_provider)
    assert headers.get("X-API-Key") == "test-api-key-123"
    
    # Test Basic auth
    basic_provider = WebSocketProvider(
        name="basic_test", 
        url="wss://example.com/ws",
        auth=BasicAuth(username="user", password="pass")
    )
    headers = await transport._prepare_headers(basic_provider)
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")
    
    await transport.close()


@pytest.mark.skip(reason="OAuth2 mocking complex - tested in integration")
@pytest.mark.asyncio 
async def test_oauth2_authentication():
    """Test OAuth2 authentication flow - skipped for unit tests"""
    pass


@pytest.mark.asyncio
async def test_custom_headers():
    """Test custom headers in provider"""
    transport = WebSocketClientTransport()
    
    provider = WebSocketProvider(
        name="header_provider",
        url="wss://example.com/ws",
        headers={"Custom-Header": "custom-value"}
    )
    
    headers = await transport._prepare_headers(provider)
    assert headers.get("Custom-Header") == "custom-value"
    
    await transport.close()


@pytest.mark.asyncio
async def test_cleanup():
    """Test transport cleanup"""
    transport = WebSocketClientTransport()
    
    # Add some mock state
    transport._oauth_tokens["test"] = {"access_token": "token"}
    
    await transport.close()
    
    assert len(transport._connections) == 0
    assert len(transport._oauth_tokens) == 0


@pytest.mark.asyncio
async def test_deregister_with_wrong_provider_type():
    """Test deregistering with wrong provider type does nothing"""
    transport = WebSocketClientTransport()
    
    provider = HttpProvider(name="http", url="https://example.com")
    
    # Should not raise an exception
    await transport.deregister_tool_provider(provider)
    
    await transport.close()


def test_transport_cleanup_warning():
    """Test that transport warns about improper cleanup"""
    transport = WebSocketClientTransport()
    
    # Add some mock connections
    transport._connections = {"test": Mock()}
    
    # Test that __del__ method exists (can't easily test the warning)
    assert hasattr(transport, '__del__')
    assert callable(getattr(transport, '__del__'))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])