from utcp.data.call_template import CallTemplate, CallTemplateSerializer
from utcp.data.auth import Auth
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback
from typing import Optional, Dict, List, Literal
from pydantic import Field

class HttpCallTemplate(CallTemplate):
    """Provider configuration for HTTP-based tools.

    Supports RESTful HTTP/HTTPS APIs with various HTTP methods, authentication,
    custom headers, and flexible request/response handling. Supports URL path
    parameters using {parameter_name} syntax. All tool arguments not mapped to
    URL body, headers or query pattern parameters are passed as query parameters using '?arg_name={arg_value}'.

    Attributes:
        type: Always "http" for HTTP providers.
        http_method: The HTTP method to use for requests.
        url: The base URL for the HTTP endpoint. Supports path parameters like
            "https://api.example.com/users/{user_id}/posts/{post_id}".
        content_type: The Content-Type header for requests.
        auth: Optional authentication configuration.
        headers: Optional static headers to include in all requests.
        body_field: Name of the tool argument to map to the HTTP request body.
        header_fields: List of tool argument names to map to HTTP request headers.
    """

    call_template_type: Literal["http"] = "http"
    http_method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = "GET"
    url: str
    content_type: str = Field(default="application/json")
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    body_field: Optional[str] = Field(default="body", description="The name of the single input field to be sent as the request body.")
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers.")


class HttpCallTemplateSerializer(Serializer[HttpCallTemplate]):
    """Serializer for HttpCallTemplate."""
    
    def to_dict(self, obj: HttpCallTemplate) -> dict:
        return obj.model_dump()
    
    def validate_dict(self, obj: dict) -> HttpCallTemplate:
        try:
            return HttpCallTemplate.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid HttpCallTemplate: " + traceback.format_exc()) from e
