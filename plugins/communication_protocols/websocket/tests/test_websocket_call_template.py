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
    assert template.message is None  # No message template by default (maximum flexibility)
    assert template.response_format is None  # No format enforcement by default
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


def test_websocket_call_template_with_message_dict():
    """Test WebSocket call template with dict message template."""
    template = WebSocketCallTemplate(
        name="dict_ws",
        url="wss://api.example.com/ws",
        message={"action": "UTCP_ARG_action_UTCP_ARG", "data": "UTCP_ARG_data_UTCP_ARG", "id": "123"}
    )
    assert template.message == {"action": "UTCP_ARG_action_UTCP_ARG", "data": "UTCP_ARG_data_UTCP_ARG", "id": "123"}


def test_websocket_call_template_with_message_string():
    """Test WebSocket call template with string message template."""
    template = WebSocketCallTemplate(
        name="string_ws",
        url="wss://api.example.com/ws",
        message="CMD:UTCP_ARG_command_UTCP_ARG;VALUE:UTCP_ARG_value_UTCP_ARG"
    )
    assert template.message == "CMD:UTCP_ARG_command_UTCP_ARG;VALUE:UTCP_ARG_value_UTCP_ARG"


def test_websocket_call_template_serialization():
    """Test WebSocket call template serialization."""
    template = WebSocketCallTemplate(
        name="test_ws",
        url="wss://api.example.com/ws",
        protocol="utcp-v1",
        timeout=60,
        message={"type": "UTCP_ARG_type_UTCP_ARG"},
        response_format="json"
    )

    serializer = WebSocketCallTemplateSerializer()
    data = serializer.to_dict(template)

    assert data["name"] == "test_ws"
    assert data["call_template_type"] == "websocket"
    assert data["url"] == "wss://api.example.com/ws"
    assert data["protocol"] == "utcp-v1"
    assert data["timeout"] == 60
    assert data["message"] == {"type": "UTCP_ARG_type_UTCP_ARG"}
    assert data["response_format"] == "json"

    # Deserialize
    restored = serializer.validate_dict(data)
    assert restored.name == template.name
    assert restored.url == template.url
    assert restored.protocol == template.protocol
    assert restored.message == template.message


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


def test_websocket_call_template_response_format():
    """Test WebSocket call template with response format specification."""
    template = WebSocketCallTemplate(
        name="format_ws",
        url="wss://api.example.com/ws",
        response_format="json"
    )
    assert template.response_format == "json"

    template2 = WebSocketCallTemplate(
        name="text_ws",
        url="wss://api.example.com/ws",
        response_format="text"
    )
    assert template2.response_format == "text"
