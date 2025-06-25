from typing import Dict, Any, Optional, List, Literal, TypeAlias, Union
from pydantic import BaseModel, Field

from utcp.shared.auth import (
    Auth,
    ApiKeyAuth,
    BasicAuth,
    OAuth2Auth,
)

ProviderType: TypeAlias = Literal[
    'http',  # RESTful HTTP/HTTPS API
    'sse',  # Server-Sent Events
    'http_stream',  # HTTP Chunked Transfer Encoding
    'cli',  # Command Line Interface
    'websocket',  # WebSocket bidirectional connection
    'grpc',  # gRPC (Google Remote Procedure Call)
    'graphql',  # GraphQL query language
    'tcp',  # Raw TCP socket
    'udp',  # User Datagram Protocol
    'webrtc',  # Web Real-Time Communication
    'mcp',  # Model Context Protocol
]

class Provider(BaseModel):
    name: str
    provider_type: ProviderType
    startup_command: Optional[List[str]] = None  # For launching the provider if needed

class HttpProvider(Provider):
    """Options specific to HTTP tools"""

    provider_type: Literal["http"] = "http"
    http_method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = "POST"
    url: str
    content_type: str = "application/json"
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    body_field: Optional[str] = Field(default=None, description="The name of the single input field to be sent as the request body.")
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers.")

class SSEProvider(Provider):
    """Options specific to Server-Sent Events tools"""

    provider_type: Literal["sse"] = "sse"
    url: str
    event_type: Optional[str] = None
    reconnect: bool = True
    retry_timeout: int = 30000  # Retry timeout in milliseconds if disconnected
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    body_field: Optional[str] = Field(default=None, description="The name of the single input field to be sent as the request body.")
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers for the initial connection.")

class StreamableHttpProvider(Provider):
    """Options specific to HTTP Chunked Transfer Encoding (HTTP streaming) tools"""

    provider_type: Literal["http_stream"] = "http_stream"
    url: str
    http_method: Literal["GET", "POST"] = "GET"
    content_type: str = "application/octet-stream"
    chunk_size: int = 4096  # Size of chunks in bytes
    timeout: int = 60000  # Timeout in milliseconds
    headers: Optional[Dict[str, str]] = None
    auth: Optional[Auth] = None
    body_field: Optional[str] = Field(default=None, description="The name of the single input field to be sent as the request body.")
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers.")

class CliProvider(Provider):
    """Options specific to CLI tools"""

    provider_type: Literal["cli"] = "cli"
    command_name: Optional[str] = None  # If None, will use the tool name
    auth: Optional[Union[ApiKeyAuth, BasicAuth]] = None

class WebSocketProvider(Provider):
    """Options specific to WebSocket tools"""

    provider_type: Literal["websocket"] = "websocket"
    url: str
    protocol: Optional[str] = None
    keep_alive: bool = True
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers for the initial connection.")

class GRPCProvider(Provider):
    """Options specific to gRPC tools"""

    provider_type: Literal["grpc"] = "grpc"
    host: str
    port: int
    service_name: str
    method_name: str
    use_ssl: bool = False
    auth: Optional[Auth] = None

class GraphQLProvider(Provider):
    """Options specific to GraphQL tools"""

    provider_type: Literal["graphql"] = "graphql"
    url: str
    operation_type: Literal["query", "mutation", "subscription"] = "query"
    operation_name: Optional[str] = None
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers for the initial connection.")

class TCPProvider(Provider):
    """Options specific to raw TCP socket tools"""

    provider_type: Literal["tcp"] = "tcp"
    host: str
    port: int
    timeout: int = 30000
    auth: None = None

class UDPProvider(Provider):
    """Options specific to UDP socket tools"""

    provider_type: Literal["udp"] = "udp"
    host: str
    port: int
    timeout: int = 30000
    auth: None = None

class WebRTCProvider(Provider):
    """Options specific to WebRTC tools"""

    provider_type: Literal["webrtc"] = "webrtc"
    signaling_server: str
    peer_id: str
    data_channel_name: str = "tools"
    auth: None = None

class McpServer(BaseModel):
    command: str
    args: Optional[List[str]] = []
    env: Optional[Dict[str, str]] = {}

class McpConfig(BaseModel):
    mcpServers: Dict[str, McpServer]

class MCPProvider(Provider):
    """Options specific to MCP tools"""

    provider_type: Literal["mcp"] = "mcp"
    config: McpConfig  # The JSON configuration for the MCP server
    auth: Optional[Auth] = None
