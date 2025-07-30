from typing import Dict, Any, Optional, List, Literal, TypeAlias, Union
from pydantic import BaseModel, Field
from typing import Annotated
import uuid
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
    'text', # Text file provider
]

class Provider(BaseModel):
    name: str = uuid.uuid4().hex
    provider_type: ProviderType

class HttpProvider(Provider):
    """Options specific to HTTP tools"""

    provider_type: Literal["http"] = "http"
    http_method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = "GET"
    url: str
    content_type: str = Field(default="application/json")
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    body_field: Optional[str] = Field(default="body", description="The name of the single input field to be sent as the request body.")
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
    command_name: str
    env_vars: Optional[Dict[str, str]] = Field(default=None, description="Environment variables to set when executing the command")
    working_dir: Optional[str] = Field(default=None, description="Working directory for command execution")
    auth: None = None

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
    """Options specific to UDP socket tools
    
    For request data handling:
    - If request_data_format is 'json', arguments will be formatted as a JSON object and sent
    - If request_data_format is 'text', the request_data_template can contain placeholders
      in the format UTCP_ARG_argname_UTCP_ARG which will be replaced with the value of 
      the argument named 'argname'
    
    For response data handling:
    - If response_byte_format is None, raw bytes will be returned
    - If response_byte_format is an encoding (e.g., 'utf-8'), bytes will be decoded to text
    """

    provider_type: Literal["udp"] = "udp"
    host: str
    port: int
    number_of_response_datagrams: int = 0
    request_data_format: Literal["json", "text"] = "json"
    request_data_template: Optional[str] = None
    response_byte_format: Optional[str] = Field(default="utf-8", description="Encoding to decode response bytes. If None, returns raw bytes.")
    timeout: int = 30000
    auth: None = None

class WebRTCProvider(Provider):
    """Options specific to WebRTC tools"""

    provider_type: Literal["webrtc"] = "webrtc"
    signaling_server: str
    peer_id: str
    data_channel_name: str = "tools"
    auth: None = None

class McpStdioServer(BaseModel):
    """Configuration for an MCP server connected via stdio."""
    transport: Literal["stdio"] = "stdio"
    command: str
    args: Optional[List[str]] = []
    env: Optional[Dict[str, str]] = {}

class McpHttpServer(BaseModel):
    """Configuration for an MCP server connected via streamable HTTP."""
    transport: Literal["http"] = "http"
    url: str

McpServer: TypeAlias = Union[McpStdioServer, McpHttpServer]

class McpConfig(BaseModel):
    mcpServers: Dict[str, McpServer]

class MCPProvider(Provider):
    """Options specific to MCP tools, supporting both stdio and HTTP transports."""

    provider_type: Literal["mcp"] = "mcp"
    config: McpConfig
    auth: Optional[OAuth2Auth] = None


class TextProvider(Provider):
    """Options specific to text file-based tools.

    This provider reads tool definitions from a local text file. This is useful
    when the tool call is included in the startup command, but the result of the
    tool call produces a file at a static location that can be read from. It can
    also be used as a UTCP tool provider to specify tools that should be used
    from different other providers.
    """

    provider_type: Literal["text"] = "text"
    file_path: str = Field(..., description="The path to the file containing the tool definitions.")
    auth: None = None

ProviderUnion = Annotated[
    Union[
        HttpProvider,
        SSEProvider,
        StreamableHttpProvider,
        CliProvider,
        WebSocketProvider,
        GRPCProvider,
        GraphQLProvider,
        TCPProvider,
        UDPProvider,
        WebRTCProvider,
        MCPProvider,
        TextProvider
    ],
    Field(discriminator="provider_type")
]