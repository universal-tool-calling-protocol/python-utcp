from utcp.data.call_template import CallTemplate
from typing import Optional, Literal
from pydantic import Field
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class TCPProvider(CallTemplate):
    """Provider configuration for raw TCP socket tools.

    Enables direct communication with TCP servers using custom protocols.
    Supports flexible request formatting, response decoding, and multiple
    framing strategies for message boundaries.

    Request Data Handling:
        - 'json' format: Arguments formatted as JSON object
        - 'text' format: Template-based with UTCP_ARG_argname_UTCP_ARG placeholders

    Response Data Handling:
        - If response_byte_format is None: Returns raw bytes
        - If response_byte_format is encoding string: Decodes bytes to text

    TCP Stream Framing Options:
        1. Length-prefix: Set framing_strategy='length_prefix' + length_prefix_bytes
        2. Delimiter-based: Set framing_strategy='delimiter' + message_delimiter
        3. Fixed-length: Set framing_strategy='fixed_length' + fixed_message_length
        4. Stream-based: Set framing_strategy='stream' (reads until connection closes)

    Attributes:
        call_template_type: Always "tcp" for TCP providers.
        host: The hostname or IP address of the TCP server.
        port: The port number of the TCP server.
        request_data_format: Format for request data ('json' or 'text').
        request_data_template: Template string for 'text' format with placeholders.
        response_byte_format: Encoding for response decoding (None for raw bytes).
        framing_strategy: Method for detecting message boundaries.
        length_prefix_bytes: Number of bytes for length prefix (1, 2, 4, or 8).
        length_prefix_endian: Byte order for length prefix ('big' or 'little').
        message_delimiter: Delimiter string for message boundaries.
        fixed_message_length: Fixed length in bytes for each message.
        max_response_size: Maximum bytes to read for stream-based framing.
        timeout: Connection timeout in milliseconds.
        auth: Always None - TCP providers don't support authentication.
    """

    call_template_type: Literal["tcp"] = "tcp"
    host: str
    port: int
    request_data_format: Literal["json", "text"] = "json"
    request_data_template: Optional[str] = None
    response_byte_format: Optional[str] = Field(default="utf-8", description="Encoding to decode response bytes. If None, returns raw bytes.")
    # TCP Framing Strategy
    framing_strategy: Literal["length_prefix", "delimiter", "fixed_length", "stream"] = Field(
        default="stream",
        description="Strategy for framing TCP messages"
    )
    # Length-prefix framing options
    length_prefix_bytes: Literal[1, 2, 4, 8] = Field(
        default=4,
        description="Number of bytes for length prefix (1, 2, 4, or 8). Used with 'length_prefix' framing."
    )
    length_prefix_endian: Literal["big", "little"] = Field(
        default="big",
        description="Byte order for length prefix. Used with 'length_prefix' framing."
    )
    # Delimiter-based framing options
    message_delimiter: str = Field(
        default='\x00',
        description="Delimiter to detect end of TCP response (e.g., '\n', '\r\n', '\x00'). Used with 'delimiter' framing."
    )
    # Fixed-length framing options
    fixed_message_length: Optional[int] = Field(
        default=None,
        description="Fixed length of each message in bytes. Used with 'fixed_length' framing."
    )
    # Stream-based options
    max_response_size: int = Field(
        default=65536,
        description="Maximum bytes to read from TCP stream. Used with 'stream' framing."
    )
    timeout: int = 30000
    auth: None = None


class TCPProviderSerializer(Serializer[TCPProvider]):
    def to_dict(self, obj: TCPProvider) -> dict:
        return obj.model_dump()

    def validate_dict(self, data: dict) -> TCPProvider:
        try:
            return TCPProvider.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError(
                f"Invalid TCPProvider: {e}\n{traceback.format_exc()}"
            )
