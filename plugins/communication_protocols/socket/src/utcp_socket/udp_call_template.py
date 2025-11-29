from utcp.data.call_template import CallTemplate
from typing import Optional, Literal
from pydantic import Field
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class UDPProvider(CallTemplate):
    """Provider configuration for UDP (User Datagram Protocol) socket tools.

    Enables communication with UDP servers using the connectionless UDP protocol.
    Supports flexible request formatting, response decoding, and multi-datagram
    response handling.

    Request Data Handling:
        - 'json' format: Arguments formatted as JSON object
        - 'text' format: Template-based with UTCP_ARG_argname_UTCP_ARG placeholders

    Response Data Handling:
        - If response_byte_format is None: Returns raw bytes
        - If response_byte_format is encoding string: Decodes bytes to text

    Attributes:
        call_template_type: Always "udp" for UDP providers.
        host: The hostname or IP address of the UDP server.
        port: The port number of the UDP server.
        number_of_response_datagrams: Expected number of response datagrams (0 for no response).
        request_data_format: Format for request data ('json' or 'text').
        request_data_template: Template string for 'text' format with placeholders.
        response_byte_format: Encoding for response decoding (None for raw bytes).
        timeout: Request timeout in milliseconds.
        auth: Always None - UDP providers don't support authentication.
    """

    call_template_type: Literal["udp"] = "udp"
    host: str
    port: int
    number_of_response_datagrams: int = 1
    request_data_format: Literal["json", "text"] = "json"
    request_data_template: Optional[str] = None
    response_byte_format: Optional[str] = Field(default="utf-8", description="Encoding to decode response bytes. If None, returns raw bytes.")
    timeout: int = 30000
    auth: None = None


class UDPProviderSerializer(Serializer[UDPProvider]):
    def to_dict(self, obj: UDPProvider) -> dict:
        return obj.model_dump()

    def validate_dict(self, data: dict) -> UDPProvider:
        try:
            return UDPProvider.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError(
                f"Invalid UDPProvider: {e}\n{traceback.format_exc()}"
            )
