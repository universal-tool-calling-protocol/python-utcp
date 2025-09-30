"""Tests for WebSocket call template."""

import pytest
from pydantic import ValidationError
from utcp_websocket.websocket_call_template import WebSocketCallTemplate, WebSocketCallTemplateSerializer


def test_websocket_call_template_basic():
    """Test basic WebSocket call template creation."""
    template = WebSocketCallTemplate(
        name="test_ws",
        url="wss://api.example.com/ws"
    )
    assert template.name == "test_ws"
    assert template.url == "wss://api.example.com/ws"
    assert template.call_template_type == "websocket"
    assert template.keep_alive is True
    assert template.request_data_format == "json"
    assert template.timeout == 30


def test_websocket_call_template_localhost():
    """Test WebSocket call template with localhost URL."""
    template = WebSocketCallTemplate(
        name="local_ws",
        url="ws://localhost:8080/ws"
    )
    assert template.url == "ws://localhost:8080/ws"


def test_websocket_call_template_invalid_url():
    """Test WebSocket call template rejects insecure URLs."""
    with pytest.raises(ValidationError) as exc_info:
        WebSocketCallTemplate(
            name="insecure_ws",
            url="ws://remote.example.com/ws"
        )
    assert "wss://" in str(exc_info.value)


def test_websocket_call_template_with_auth():
    """Test WebSocket call template with authentication."""
    from utcp.data.auth_implementations.api_key_auth import ApiKeyAuth

    template = WebSocketCallTemplate(
        name="auth_ws",
        url="wss://api.example.com/ws",
        auth=ApiKeyAuth(
            api_key="test-key",
            var_name="Authorization",
            location="header"
        )
    )
    assert template.auth is not None
    assert template.auth.api_key == "test-key"


def test_websocket_call_template_text_format():
    """Test WebSocket call template with text format."""
    template = WebSocketCallTemplate(
        name="text_ws",
        url="wss://api.example.com/ws",
        request_data_format="text",
        request_data_template="CMD:UTCP_ARG_command_UTCP_ARG"
    )
    assert template.request_data_format == "text"
    assert template.request_data_template == "CMD:UTCP_ARG_command_UTCP_ARG"


def test_websocket_call_template_serialization():
    """Test WebSocket call template serialization."""
    template = WebSocketCallTemplate(
        name="test_ws",
        url="wss://api.example.com/ws",
        protocol="utcp-v1",
        timeout=60
    )

    serializer = WebSocketCallTemplateSerializer()
    data = serializer.to_dict(template)

    assert data["name"] == "test_ws"
    assert data["call_template_type"] == "websocket"
    assert data["url"] == "wss://api.example.com/ws"
    assert data["protocol"] == "utcp-v1"
    assert data["timeout"] == 60

    # Deserialize
    restored = serializer.validate_dict(data)
    assert restored.name == template.name
    assert restored.url == template.url
    assert restored.protocol == template.protocol


def test_websocket_call_template_with_headers():
    """Test WebSocket call template with custom headers."""
    template = WebSocketCallTemplate(
        name="headers_ws",
        url="wss://api.example.com/ws",
        headers={"X-Custom": "value"},
        header_fields=["user_id"]
    )
    assert template.headers == {"X-Custom": "value"}
    assert template.header_fields == ["user_id"]


def test_websocket_call_template_legacy_message_format():
    """Test WebSocket call template with legacy message_format."""
    template = WebSocketCallTemplate(
        name="legacy_ws",
        url="wss://api.example.com/ws",
        message_format="{tool_name}:{arguments}"
    )
    assert template.message_format == "{tool_name}:{arguments}"
