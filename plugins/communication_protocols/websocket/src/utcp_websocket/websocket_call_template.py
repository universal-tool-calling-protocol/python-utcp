from utcp.data.call_template import CallTemplate, CallTemplateSerializer
from utcp.data.auth import Auth, AuthSerializer
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback
from typing import Optional, Dict, List, Literal, Union, Any
from pydantic import Field, field_serializer, field_validator

class WebSocketCallTemplate(CallTemplate):
    """REQUIRED
    Call template configuration for WebSocket-based tools.

    Supports real-time bidirectional communication via WebSocket protocol with
    various message formats, authentication methods, and connection management features.

    Configuration Examples:
        Basic WebSocket connection:
        ```json
        {
          "name": "realtime_service",
          "call_template_type": "websocket",
          "url": "wss://api.example.com/ws"
        }
        ```

        With authentication:
        ```json
        {
          "name": "secure_websocket",
          "call_template_type": "websocket",
          "url": "wss://api.example.com/ws",
          "auth": {
            "auth_type": "api_key",
            "api_key": "${WS_API_KEY}",
            "var_name": "Authorization",
            "location": "header"
          },
          "keep_alive": true,
          "protocol": "utcp-v1"
        }
        ```

        Custom message format:
        ```json
        {
          "name": "custom_format_ws",
          "call_template_type": "websocket",
          "url": "wss://api.example.com/ws",
          "request_data_format": "text",
          "request_data_template": "CMD:UTCP_ARG_command_UTCP_ARG;DATA:UTCP_ARG_data_UTCP_ARG",
          "timeout": 60
        }
        ```

    Attributes:
        call_template_type: Always "websocket" for WebSocket providers.
        url: WebSocket URL (must be wss:// or ws://localhost).
        message: Message template with UTCP_ARG_arg_name_UTCP_ARG placeholders for flexible formatting.
        protocol: Optional WebSocket subprotocol to use.
        keep_alive: Whether to maintain persistent connection with heartbeat.
        response_format: Expected response format ("json", "text", or "raw"). If None, returns raw response.
        timeout: Timeout in seconds for WebSocket operations.
        headers: Optional static headers to include in WebSocket handshake.
        header_fields: List of tool argument names to map to WebSocket handshake headers.
        auth: Optional authentication configuration for WebSocket connection.
    """
    call_template_type: Literal["websocket"] = Field(default="websocket")
    url: str = Field(..., description="WebSocket URL (wss:// or ws://localhost)")
    message: Optional[Union[str, Dict[str, Any]]] = Field(
        default=None,
        description="Message template. Can be a string or dict with UTCP_ARG_arg_name_UTCP_ARG placeholders"
    )
    protocol: Optional[str] = Field(default=None, description="WebSocket subprotocol")
    keep_alive: bool = Field(default=True, description="Enable persistent connection with heartbeat")
    response_format: Optional[Literal["json", "text", "raw"]] = Field(
        default=None,
        description="Expected response format. If None, returns raw response"
    )
    timeout: int = Field(default=30, description="Timeout in seconds for WebSocket operations")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Static headers for WebSocket handshake")
    header_fields: Optional[List[str]] = Field(default=None, description="Tool arguments to map to headers")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate WebSocket URL format."""
        if not (v.startswith("wss://") or v.startswith("ws://localhost") or v.startswith("ws://127.0.0.1")):
            raise ValueError(
                f"WebSocket URL must use wss:// or start with ws://localhost or ws://127.0.0.1. Got: {v}"
            )
        return v

    @field_serializer("headers", when_used="unless-none")
    def serialize_headers(self, headers: Optional[Dict[str, str]], _info):
        return headers if headers else None

    @field_serializer("header_fields", when_used="unless-none")
    def serialize_header_fields(self, header_fields: Optional[List[str]], _info):
        return header_fields if header_fields else None


class WebSocketCallTemplateSerializer(Serializer[WebSocketCallTemplate]):
    """REQUIRED
    Serializer for WebSocket call templates.

    Handles conversion between WebSocketCallTemplate objects and dictionaries
    for storage, transmission, and configuration parsing.
    """

    def to_dict(self, obj: WebSocketCallTemplate) -> dict:
        """Convert WebSocketCallTemplate to dictionary.

        Args:
            obj: The WebSocketCallTemplate object to convert.

        Returns:
            Dictionary representation of the call template.
        """
        result = {
            "name": obj.name,
            "call_template_type": obj.call_template_type,
            "url": obj.url,
        }

        if obj.message is not None:
            result["message"] = obj.message
        if obj.protocol is not None:
            result["protocol"] = obj.protocol
        if obj.keep_alive is not True:
            result["keep_alive"] = obj.keep_alive
        if obj.response_format is not None:
            result["response_format"] = obj.response_format
        if obj.timeout != 30:
            result["timeout"] = obj.timeout
        if obj.headers:
            result["headers"] = obj.headers
        if obj.header_fields:
            result["header_fields"] = obj.header_fields
        if obj.auth:
            result["auth"] = AuthSerializer().to_dict(obj.auth)

        return result

    def validate_dict(self, obj: dict) -> WebSocketCallTemplate:
        """Validate dictionary and convert to WebSocketCallTemplate.

        Args:
            obj: Dictionary to validate and convert.

        Returns:
            WebSocketCallTemplate object.

        Raises:
            UtcpSerializerValidationError: If validation fails.
        """
        try:
            # Parse auth if present
            if "auth" in obj and obj["auth"] is not None:
                obj["auth"] = AuthSerializer().validate_dict(obj["auth"])

            return WebSocketCallTemplate(**obj)
        except Exception as e:
            raise UtcpSerializerValidationError(
                f"Failed to validate WebSocketCallTemplate: {str(e)}\n{traceback.format_exc()}"
            )
