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

from typing import List, Optional, Union
from pydantic import BaseModel, field_serializer, field_validator, Field
import uuid
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback
from utcp.data.auth import Auth, AuthSerializer

class CallTemplate(BaseModel):
    """Base class for all UTCP tool providers.

    This is the abstract base class that all specific call template implementations
    inherit from. It provides the common fields that every provider must have.

    Attributes:
        name: Unique identifier for the provider. Defaults to a random UUID hex string.
            Should be unique across all providers and recommended to be set to a human-readable name.
            Can only contain letters, numbers and underscores. All special characters must be replaced with underscores.
        call_template_type: The transport protocol type used by this provider.
    """
    
    name: str = Field(default_factory=lambda: uuid.uuid4().hex)
    call_template_type: str
    auth: Optional[Auth] = None

    @field_serializer("auth")
    def serialize_auth(self, auth: Optional[Auth]):
        if auth is None:
            return None
        return AuthSerializer().to_dict(auth)

    @field_validator("auth", mode="before")
    @classmethod
    def validate_auth(cls, v: Optional[Union[Auth, dict]]):
        if v is None:
            return None
        if isinstance(v, Auth):
            return v
        return AuthSerializer().validate_dict(v)

class CallTemplateSerializer(Serializer[CallTemplate]):
    call_template_serializers: dict[str, Serializer[CallTemplate]] = {}

    def to_dict(self, obj: CallTemplate) -> dict:
        return CallTemplateSerializer.call_template_serializers[obj.call_template_type].to_dict(obj)
    
    def validate_dict(self, obj: dict) -> CallTemplate:
        try:
            return CallTemplateSerializer.call_template_serializers[obj["call_template_type"]].validate_dict(obj)
        except KeyError:
            raise ValueError(f"Invalid call template type: {obj['call_template_type']}")
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid CallTemplate: " + traceback.format_exc()) from e
