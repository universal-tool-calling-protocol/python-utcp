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
    'websocket',  # WebSocket bidirectional connection (WIP)
    'grpc',  # gRPC (Google Remote Procedure Call) (WIP)
    'graphql',  # GraphQL query language
    'tcp',  # Raw TCP socket
    'udp',  # User Datagram Protocol
    'webrtc',  # Web Real-Time Communication (WIP)
    'mcp',  # Model Context Protocol
    'text', # Text file provider
]
"""Type alias for all supported provider transport types.

This literal type defines all the communication protocols and transport
mechanisms that UTCP supports for connecting to tool providers.
"""

class Provider(BaseModel):
    """Base class for all UTCP tool providers.

    This is the abstract base class that all specific provider implementations
    inherit from. It provides the common fields that every provider must have.

    Attributes:
        name: Unique identifier for the provider. Defaults to a random UUID hex string. 
            Should be unique across all providers and recommended to be set to a human-readable name.
            Can only contain letters, numbers and underscores. All special characters must be replaced with underscores.
        provider_type: The transport protocol type used by this provider.
    """
    
    name: str = uuid.uuid4().hex
    provider_type: ProviderType

class HttpProvider(Provider):
    """Provider configuration for HTTP-based tools.

    Supports RESTful HTTP/HTTPS APIs with various HTTP methods, authentication,
    custom headers, and flexible request/response handling. Supports URL path
    parameters using {parameter_name} syntax. All tool arguments not mapped to
    URL body, headers or query pattern parameters are passed as query parameters using '?arg_name={arg_value}'.

    Attributes:
        provider_type: Always "http" for HTTP providers.
        http_method: The HTTP method to use for requests.
        url: The base URL for the HTTP endpoint. Supports path parameters like
            "https://api.example.com/users/{user_id}/posts/{post_id}".
        content_type: The Content-Type header for requests.
        auth: Optional authentication configuration.
        headers: Optional static headers to include in all requests.
        body_field: Name of the tool argument to map to the HTTP request body.
        header_fields: List of tool argument names to map to HTTP request headers.
    """

    provider_type: Literal["http"] = "http"
    http_method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = "GET"
    url: str
    content_type: str = Field(default="application/json")
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    body_field: Optional[str] = Field(default="body", description="The name of the single input field to be sent as the request body.")
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers.")

class SSEProvider(Provider):
    """Provider configuration for Server-Sent Events (SSE) tools.

    Enables real-time streaming of events from server to client using the
    Server-Sent Events protocol. Supports automatic reconnection and
    event type filtering. All tool arguments not mapped to URL body, headers
    or query pattern parameters are passed as query parameters using '?arg_name={arg_value}'.

    Attributes:
        provider_type: Always "sse" for SSE providers.
        url: The SSE endpoint URL to connect to.
        event_type: Optional filter for specific event types. If None, all events are received.
        reconnect: Whether to automatically reconnect on connection loss.
        retry_timeout: Timeout in milliseconds before attempting reconnection.
        auth: Optional authentication configuration.
        headers: Optional static headers for the initial connection.
        body_field: Optional tool argument name to map to request body during connection.
        header_fields: List of tool argument names to map to HTTP headers during connection.
    """

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
    """Provider configuration for HTTP streaming tools.

    Uses HTTP Chunked Transfer Encoding to enable streaming of large responses
    or real-time data. Useful for tools that return large datasets or provide
    progressive results. All tool arguments not mapped to URL body, headers
    or query pattern parameters are passed as query parameters using '?arg_name={arg_value}'.

    Attributes:
        provider_type: Always "http_stream" for HTTP streaming providers.
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
    """Provider configuration for Command Line Interface tools.

    Enables execution of command-line tools and programs as UTCP providers.
    Supports environment variable injection and custom working directories.

    Attributes:
        provider_type: Always "cli" for CLI providers.
        command_name: The name or path of the command to execute.
        env_vars: Optional environment variables to set during command execution.
        working_dir: Optional custom working directory for command execution.
        auth: Always None - CLI providers don't support authentication.
    """

    provider_type: Literal["cli"] = "cli"
    command_name: str
    env_vars: Optional[Dict[str, str]] = Field(default=None, description="Environment variables to set when executing the command")
    working_dir: Optional[str] = Field(default=None, description="Working directory for command execution")
    auth: None = None

class WebSocketProvider(Provider):
    """Provider configuration for WebSocket-based tools. (WIP)

    Enables bidirectional real-time communication with WebSocket servers.
    Supports custom protocols, keep-alive functionality, and authentication.

    Attributes:
        provider_type: Always "websocket" for WebSocket providers.
        url: The WebSocket endpoint URL (ws:// or wss://).
        protocol: Optional WebSocket sub-protocol to request.
        keep_alive: Whether to maintain the connection with keep-alive messages.
        auth: Optional authentication configuration.
        headers: Optional static headers for the WebSocket handshake.
        header_fields: List of tool argument names to map to headers during handshake.
    """

    provider_type: Literal["websocket"] = "websocket"
    url: str
    protocol: Optional[str] = None
    keep_alive: bool = True
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers for the initial connection.")

class GRPCProvider(Provider):
    """Provider configuration for gRPC (Google Remote Procedure Call) tools. (WIP)

    Enables communication with gRPC services using the Protocol Buffers
    serialization format. Supports both secure (TLS) and insecure connections.

    Attributes:
        provider_type: Always "grpc" for gRPC providers.
        host: The hostname or IP address of the gRPC server.
        port: The port number of the gRPC server.
        service_name: The name of the gRPC service to call.
        method_name: The name of the gRPC method to invoke.
        use_ssl: Whether to use SSL/TLS for secure connections.
        auth: Optional authentication configuration.
    """

    provider_type: Literal["grpc"] = "grpc"
    host: str
    port: int
    service_name: str
    method_name: str
    use_ssl: bool = False
    auth: Optional[Auth] = None

class GraphQLProvider(Provider):
    """Provider configuration for GraphQL-based tools.

    Enables communication with GraphQL endpoints supporting queries, mutations,
    and subscriptions. Provides flexible query execution with custom headers
    and authentication.

    Attributes:
        provider_type: Always "graphql" for GraphQL providers.
        url: The GraphQL endpoint URL.
        operation_type: The type of GraphQL operation (query, mutation, subscription).
        operation_name: Optional name for the GraphQL operation.
        auth: Optional authentication configuration.
        headers: Optional static headers to include in requests.
        header_fields: List of tool argument names to map to HTTP request headers.
    """

    provider_type: Literal["graphql"] = "graphql"
    url: str
    operation_type: Literal["query", "mutation", "subscription"] = "query"
    operation_name: Optional[str] = None
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers for the initial connection.")

class TCPProvider(Provider):
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
        provider_type: Always "tcp" for TCP providers.
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

    provider_type: Literal["tcp"] = "tcp"
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
        default='\\x00',
        description="Delimiter to detect end of TCP response (e.g., '\\n', '\\r\\n', '\\x00'). Used with 'delimiter' framing."
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

class UDPProvider(Provider):
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
        provider_type: Always "udp" for UDP providers.
        host: The hostname or IP address of the UDP server.
        port: The port number of the UDP server.
        number_of_response_datagrams: Expected number of response datagrams (0 for no response).
        request_data_format: Format for request data ('json' or 'text').
        request_data_template: Template string for 'text' format with placeholders.
        response_byte_format: Encoding for response decoding (None for raw bytes).
        timeout: Request timeout in milliseconds.
        auth: Always None - UDP providers don't support authentication.
    """

    provider_type: Literal["udp"] = "udp"
    host: str
    port: int
    number_of_response_datagrams: int = 1
    request_data_format: Literal["json", "text"] = "json"
    request_data_template: Optional[str] = None
    response_byte_format: Optional[str] = Field(default="utf-8", description="Encoding to decode response bytes. If None, returns raw bytes.")
    timeout: int = 30000
    auth: None = None

class WebRTCProvider(Provider):
    """Provider configuration for WebRTC (Web Real-Time Communication) tools.

    Enables peer-to-peer communication using WebRTC data channels.
    Requires a signaling server to establish the initial connection.

    Attributes:
        provider_type: Always "webrtc" for WebRTC providers.
        signaling_server: URL of the signaling server for peer discovery.
        peer_id: Unique identifier for this peer in the WebRTC network.
        data_channel_name: Name of the data channel for tool communication.
        auth: Always None - WebRTC providers don't support authentication.
    """

    provider_type: Literal["webrtc"] = "webrtc"
    signaling_server: str
    peer_id: str
    data_channel_name: str = "tools"
    auth: None = None

class McpStdioServer(BaseModel):
    """Configuration for an MCP server connected via stdio transport.

    Enables communication with Model Context Protocol servers through
    standard input/output streams, typically used for local processes.

    Attributes:
        transport: Always "stdio" for stdio-based MCP servers.
        command: The command to execute to start the MCP server.
        args: Optional command-line arguments for the MCP server.
        env: Optional environment variables for the MCP server process.
    """
    transport: Literal["stdio"] = "stdio"
    command: str
    args: Optional[List[str]] = []
    env: Optional[Dict[str, str]] = {}

class McpHttpServer(BaseModel):
    """Configuration for an MCP server connected via HTTP transport.

    Enables communication with Model Context Protocol servers through
    HTTP connections, typically used for remote MCP services.

    Attributes:
        transport: Always "http" for HTTP-based MCP servers.
        url: The HTTP endpoint URL for the MCP server.
    """
    transport: Literal["http"] = "http"
    url: str

McpServer: TypeAlias = Union[McpStdioServer, McpHttpServer]
"""Type alias for MCP server configurations.

Union type for all supported MCP server transport configurations,
including both stdio and HTTP-based servers.
"""

class McpConfig(BaseModel):
    """Configuration container for multiple MCP servers.

    Holds a collection of named MCP server configurations, allowing
    a single MCP provider to manage multiple server connections.

    Attributes:
        mcpServers: Dictionary mapping server names to their configurations.
    """
    
    mcpServers: Dict[str, McpServer]

class MCPProvider(Provider):
    """Provider configuration for Model Context Protocol (MCP) tools.

    Enables communication with MCP servers that provide structured tool
    interfaces. Supports both stdio (local process) and HTTP (remote)
    transport methods.

    Attributes:
        provider_type: Always "mcp" for MCP providers.
        config: Configuration object containing MCP server definitions.
            This follows the same format as the official MCP server configuration.
        auth: Optional OAuth2 authentication for HTTP-based MCP servers.
    """

    provider_type: Literal["mcp"] = "mcp"
    config: McpConfig
    auth: Optional[OAuth2Auth] = None


class TextProvider(Provider):
    """Provider configuration for text file-based tools.

    Reads tool definitions from local text files, useful for static tool
    configurations or when tools generate output files at known locations.

    Use Cases:
        - Static tool definitions from configuration files
        - Tools that write results to predictable file locations
        - Download manuals from a remote server to allow inspection of tools
            before calling them and guarantee security for high-risk environments

    Attributes:
        provider_type: Always "text" for text file providers.
        file_path: Path to the file containing tool definitions.
        auth: Always None - text providers don't support authentication.
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
"""Discriminated union type for all UTCP provider configurations.

This annotated union type includes all supported provider implementations,
using 'provider_type' as the discriminator field for automatic type
resolution during deserialization.

Supported Provider Types:
    - HttpProvider: RESTful HTTP/HTTPS APIs
    - SSEProvider: Server-Sent Events streaming
    - StreamableHttpProvider: HTTP Chunked Transfer Encoding
    - CliProvider: Command Line Interface tools
    - WebSocketProvider: Bidirectional WebSocket connections
    - GRPCProvider: Google Remote Procedure Call
    - GraphQLProvider: GraphQL query language
    - TCPProvider: Raw TCP socket connections
    - UDPProvider: User Datagram Protocol
    - WebRTCProvider: Web Real-Time Communication
    - MCPProvider: Model Context Protocol
    - TextProvider: Text file-based providers
"""
