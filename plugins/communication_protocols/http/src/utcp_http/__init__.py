"""HTTP Communication Protocol plugin for UTCP.

This plugin provides HTTP-based communication protocols including:
- Standard HTTP requests
- Server-Sent Events (SSE)
- Streamable HTTP with chunked transfer encoding
"""

from utcp.discovery import register_communication_protocol, register_call_template
from utcp_http.http_communication_protocol import HttpCommunicationProtocol
from utcp_http.sse_communication_protocol import SseCommunicationProtocol
from utcp_http.streamable_http_communication_protocol import StreamableHttpCommunicationProtocol
from utcp_http.http_call_template import HttpCallTemplate, HttpCallTemplateSerializer
from utcp_http.sse_call_template import SseCallTemplate, SSECallTemplateSerializer
from utcp_http.streamable_http_call_template import StreamableHttpCallTemplate, StreamableHttpCallTemplateSerializer

# Register HTTP communication protocols
register_communication_protocol("http", HttpCommunicationProtocol())
register_communication_protocol("sse", SseCommunicationProtocol())
register_communication_protocol("streamable_http", StreamableHttpCommunicationProtocol())

# Register call template serializers
register_call_template("http", HttpCallTemplateSerializer())
register_call_template("sse", SSECallTemplateSerializer())
register_call_template("streamable_http", StreamableHttpCallTemplateSerializer())

# Export public API
__all__ = [
    "HttpCommunicationProtocol",
    "SseCommunicationProtocol",
    "StreamableHttpCommunicationProtocol",
    "HttpCallTemplate",
    "SseCallTemplate",
    "StreamableHttpCallTemplate",
    "HttpCallTemplateSerializer",
    "SSECallTemplateSerializer",
    "StreamableHttpCallTemplateSerializer",
]