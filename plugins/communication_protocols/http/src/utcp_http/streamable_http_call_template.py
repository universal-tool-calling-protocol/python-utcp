from utcp.data.call_template import CallTemplate, CallTemplateSerializer
from utcp.data.auth import Auth
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback
from typing import Optional, Dict, List, Literal
from pydantic import Field

class StreamableHttpCallTemplate(CallTemplate):
    """Provider configuration for HTTP streaming tools.

    Uses HTTP Chunked Transfer Encoding to enable streaming of large responses
    or real-time data. Useful for tools that return large datasets or provide
    progressive results. All tool arguments not mapped to URL body, headers
    or query pattern parameters are passed as query parameters using '?arg_name={arg_value}'.

    Attributes:
        call_template_type: Always "streamable_http" for HTTP streaming providers.
        url: The streaming HTTP endpoint URL. Supports path parameters.
        http_method: The HTTP method to use (GET or POST).
        content_type: The Content-Type header for requests.
        chunk_size: Size of each chunk in bytes for reading the stream.
        timeout: Request timeout in milliseconds.
        headers: Optional static headers to include in requests.
        auth: Optional authentication configuration.
        body_field: Optional tool argument name to map to HTTP request body.
        header_fields: List of tool argument names to map to HTTP request headers.
    """

    call_template_type: Literal["streamable_http"] = "streamable_http"
    url: str
    http_method: Literal["GET", "POST"] = "GET"
    content_type: str = "application/octet-stream"
    chunk_size: int = 4096  # Size of chunks in bytes
    timeout: int = 60000  # Timeout in milliseconds
    headers: Optional[Dict[str, str]] = None
    auth: Optional[Auth] = None
    body_field: Optional[str] = Field(default=None, description="The name of the single input field to be sent as the request body.")
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers.")


class StreamableHttpCallTemplateSerializer(Serializer[StreamableHttpCallTemplate]):
    """Serializer for StreamableHttpCallTemplate."""
    
    def to_dict(self, obj: StreamableHttpCallTemplate) -> dict:
        return obj.model_dump()
    
    def validate_dict(self, obj: dict) -> StreamableHttpCallTemplate:
        try:
            return StreamableHttpCallTemplate.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid StreamableHttpCallTemplate: " + traceback.format_exc()) from e
