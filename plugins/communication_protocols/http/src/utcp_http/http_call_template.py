from utcp.data.call_template import CallTemplate, CallTemplateSerializer
from utcp.data.auth import Auth, AuthSerializer
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback
from typing import Optional, Dict, List, Literal, Any
from pydantic import Field, field_serializer, field_validator

class HttpCallTemplate(CallTemplate):
    """REQUIRED
    Provider configuration for HTTP-based tools.

    Supports RESTful HTTP/HTTPS APIs with various HTTP methods, authentication,
    custom headers, and flexible request/response handling. Supports URL path
    parameters using {parameter_name} syntax. All tool arguments not mapped to
    URL body, headers or query pattern parameters are passed as query parameters using '?arg_name={arg_value}'.

    Configuration Examples:
        Basic HTTP GET request:
        ```json
        {
          "name": "my_rest_api",
          "call_template_type": "http",
          "url": "https://api.example.com/users/{user_id}",
          "http_method": "GET"
        }
        ```

        POST with authentication:
        ```json
        {
          "name": "secure_api",
          "call_template_type": "http",
          "url": "https://api.example.com/users",
          "http_method": "POST",
          "content_type": "application/json",
          "auth": {
            "auth_type": "api_key",
            "api_key": "Bearer ${API_KEY}",
            "var_name": "Authorization",
            "location": "header"
          },
          "auth_tools": {
            "auth_type": "api_key",
            "api_key": "Bearer ${TOOL_API_KEY}",
            "var_name": "Authorization",
            "location": "header"
          },
          "headers": {
            "X-Custom-Header": "value"
          },
          "body_field": "body",
          "header_fields": ["user_id"]
        }
        ```

        OAuth2 authentication:
        ```json
        {
          "name": "oauth_api",
          "call_template_type": "http",
          "url": "https://api.example.com/data",
          "http_method": "GET",
          "auth": {
            "auth_type": "oauth2",
            "client_id": "${CLIENT_ID}",
            "client_secret": "${CLIENT_SECRET}",
            "token_url": "https://auth.example.com/token"
          }
        }
        ```

        Basic authentication:
        ```json
        {
          "name": "basic_auth_api",
          "call_template_type": "http",
          "url": "https://api.example.com/secure",
          "http_method": "GET",
          "auth": {
            "auth_type": "basic",
            "username": "${USERNAME}",
            "password": "${PASSWORD}"
          }
        }
        ```

    Attributes:
        call_template_type: Always "http" for HTTP providers.
        http_method: The HTTP method to use for requests.
        url: The base URL for the HTTP endpoint. Supports path parameters like
            "https://api.example.com/users/{user_id}/posts/{post_id}".
        content_type: The Content-Type header for requests.
        auth: Optional authentication configuration for accessing the OpenAPI spec URL.
        auth_tools: Optional authentication configuration for generated tools. Applied only to endpoints requiring auth per OpenAPI spec.
        headers: Optional static headers to include in all requests.
        body_field: Name of the tool argument to map to the HTTP request body.
        header_fields: List of tool argument names to map to HTTP request headers.
    """

    call_template_type: Literal["http"] = "http"
    http_method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = "GET"
    url: str
    content_type: str = Field(default="application/json")
    auth: Optional[Auth] = None
    auth_tools: Optional[Auth] = Field(default=None, description="Authentication configuration for generated tools (applied only to endpoints requiring auth per OpenAPI spec)")
    headers: Optional[Dict[str, str]] = None
    body_field: Optional[str] = Field(default="body", description="The name of the single input field to be sent as the request body.")
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers.")

    @field_serializer('auth')
    def serialize_auth(self, auth: Optional[Auth]) -> Optional[dict]:
        """Serialize auth to dictionary."""
        if auth is None:
            return None
        return AuthSerializer().to_dict(auth)

    @field_validator('auth', mode='before')
    @classmethod
    def validate_auth(cls, v: Any) -> Optional[Auth]:
        """Validate and deserialize auth from dictionary."""
        if v is None:
            return None
        if isinstance(v, Auth):
            return v
        if isinstance(v, dict):
            return AuthSerializer().validate_dict(v)
        raise ValueError(f"auth must be None, Auth instance, or dict, got {type(v)}")

    @field_serializer('auth_tools')
    def serialize_auth_tools(self, auth_tools: Optional[Auth]) -> Optional[dict]:
        """Serialize auth_tools to dictionary."""
        if auth_tools is None:
            return None
        return AuthSerializer().to_dict(auth_tools)

    @field_validator('auth_tools', mode='before')
    @classmethod
    def validate_auth_tools(cls, v: Any) -> Optional[Auth]:
        """Validate and deserialize auth_tools from dictionary."""
        if v is None:
            return None
        if isinstance(v, Auth):
            return v
        if isinstance(v, dict):
            return AuthSerializer().validate_dict(v)
        raise ValueError(f"auth_tools must be None, Auth instance, or dict, got {type(v)}")


class HttpCallTemplateSerializer(Serializer[HttpCallTemplate]):
    """REQUIRED
    Serializer for HttpCallTemplate."""
    
    def to_dict(self, obj: HttpCallTemplate) -> dict:
        """REQUIRED
        Convert HttpCallTemplate to dictionary."""
        return obj.model_dump()
    
    def validate_dict(self, obj: dict) -> HttpCallTemplate:
        """REQUIRED
        Validate dictionary and convert to HttpCallTemplate."""
        try:
            return HttpCallTemplate.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid HttpCallTemplate: " + traceback.format_exc()) from e
