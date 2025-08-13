"""Provider configurations for UTCP tool providers.

This module defines the provider models and configurations for all supported
transport protocols in UTCP. Each provider type encapsulates the necessary
configuration to connect to and interact with tools through different
communication channels.

Supported provider types:
    - HTTP: RESTful HTTP/HTTPS APIs
    - SSE: Server-Sent Events for streaming
    - HTTP Stream: HTTP Chunked Transfer Encoding
    - CLI: Command Line Interface tools
    - WebSocket: Bidirectional WebSocket connections (WIP)
    - gRPC: Google Remote Procedure Call (WIP)
    - GraphQL: GraphQL query language
    - TCP: Raw TCP socket connections
    - UDP: User Datagram Protocol
    - WebRTC: Web Real-Time Communication (WIP)
    - MCP: Model Context Protocol
    - Text: Text file-based providers
"""

from typing import List
from pydantic import BaseModel
import uuid
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError

communication_protocol_types: List[str] = []

class CallTemplate(BaseModel):
    """Base class for all UTCP tool providers.

    This is the abstract base class that all specific call template implementations
    inherit from. It provides the common fields that every provider must have.

    Attributes:
        name: Unique identifier for the provider. Defaults to a random UUID hex string.
            Should be unique across all providers and recommended to be set to a human-readable name.
            Can only contain letters, numbers and underscores. All special characters must be replaced with underscores.
        type: The transport protocol type used by this provider.
    """
    
    name: str = uuid.uuid4().hex
    type: str

class CallTemplateSerializer(Serializer[CallTemplate]):
    call_template_serializers: dict[str, Serializer[CallTemplate]] = {}

    def to_dict(self, obj: CallTemplate) -> dict:
        return CallTemplateSerializer.call_template_serializers[obj.type].to_dict(obj)
    
    def validate_dict(self, obj: dict) -> CallTemplate:
        try:
            return CallTemplateSerializer.call_template_serializers[obj["type"]].validate_dict(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid CallTemplate: " + str(e)) from e
