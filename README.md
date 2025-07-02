# Universal Tool Calling Protocol (UTCP)

## Introduction

The Universal Tool Calling Protocol (UTCP) is a modern, flexible, and scalable standard for defining and interacting with tools across a wide variety of communication protocols. It is designed to be easy to use, interoperable, and extensible, making it a powerful choice for building and consuming tool-based services.

In contrast to other protocols like MCP, UTCP places a strong emphasis on:

*   **Scalability**: UTCP is designed to handle a large number of tools and providers without compromising performance.
*   **Interoperability**: With support for a wide range of provider types (including HTTP, WebSockets, gRPC, and even CLI tools), UTCP can integrate with almost any existing service or infrastructure.
*   **Ease of Use**: The protocol is built on simple, well-defined Pydantic models, making it easy for developers to implement and use.

## Protocol Specification

UTCP is defined by a set of core data models that describe tools, how to connect to them (providers), and how to secure them (authentication).

### Tool Discovery

A UTCP-compliant tool provider must expose an endpoint (e.g., an HTTP URL) that, when queried, returns a `UtcpResponse` object. This response contains a list of all the tools available from that provider.

#### `UtcpResponse` Model

```json
{
  "version": "string",
  "tools": [
    {
      "name": "string",
      "description": "string",
      "inputs": { ... },
      "outputs": { ... },
      "tags": ["string"],
      "provider": { ... }
    }
  ]
}
```

*   `version`: The version of the UTCP protocol being used.
*   `tools`: A list of `Tool` objects.

### Tool Definition

Each tool is defined by the `Tool` model.

#### `Tool` Model

```json
{
  "name": "string",
  "description": "string",
  "inputs": {
    "type": "object",
    "properties": { ... },
    "required": ["string"],
    "description": "string",
    "title": "string"
  },
  "outputs": { ... },
  "tags": ["string"],
  "provider": { ... }
}
```

*   `name`: The name of the tool.
*   `description`: A human-readable description of what the tool does.
*   `inputs`: A schema defining the input parameters for the tool. This follows a simplified JSON Schema format.
*   `outputs`: A schema defining the output of the tool.
*   `tags`: A list of tags for categorizing the tool making searching for relevant tools easier.
*   `provider`: The `Provider` object that describes how to connect to and use the tool.

### Providers

Providers are at the heart of UTCP's flexibility. They define the communication protocol for a given tool. UTCP supports a wide range of provider types:

*   `http`: RESTful HTTP/HTTPS API
*   `sse`: Server-Sent Events
*   `http_stream`: HTTP Chunked Transfer Encoding
*   `cli`: Command Line Interface
*   `websocket`: WebSocket bidirectional connection
*   `grpc`: gRPC (Google Remote Procedure Call)
*   `graphql`: GraphQL query language
*   `tcp`: Raw TCP socket
*   `udp`: User Datagram Protocol
*   `webrtc`: Web Real-Time Communication
*   `mcp`: Model Context Protocol (for interoperability)

Each provider type has its own specific configuration options. For example, an `HttpProvider` will have a `url` and an `http_method`.

## Provider Configuration Examples

Below are examples of how to configure each of the supported provider types in a JSON configuration file. Where possible, the tool discovery endpoint should be `/utcp`. Each tool provider should offer users their json provider configuration for the tool discovery endpoint.

### HTTP Provider

For connecting to standard RESTful APIs.

```json
{
  "name": "my_rest_api",
  "provider_type": "http",
  "url": "https://api.example.com/utcp",
  "http_method": "POST",
  "content_type": "application/json",
  "auth": {
    "auth_type": "api_key",
    "api_key": "YOUR_API_KEY",
    "var_name": "X-API-Key"
  }
}
```

### Server-Sent Events (SSE) Provider

For tools that stream data using SSE. The `url` should point to the discovery endpoint.

```json
{
  "name": "live_updates_service",
  "provider_type": "sse",
  "url": "https://api.example.com/utcp",
  "event_type": "message"
}
```

### HTTP Stream Provider

For tools that use HTTP chunked transfer encoding to stream data. The `url` should point to the discovery endpoint.

```json
{
  "name": "streaming_data_source",
  "provider_type": "http_stream",
  "url": "https://api.example.com/utcp",
  "http_method": "GET"
}
```

### CLI Provider

For wrapping local command-line tools.

```json
{
  "name": "my_cli_tool",
  "provider_type": "cli",
  "command_name": "my-command -utcp"
}
```

### WebSocket Provider

For tools that communicate over a WebSocket connection. Tool discovery may need to be handled via a separate HTTP endpoint.

```json
{
  "name": "realtime_chat_service",
  "provider_type": "websocket",
  "url": "wss://api.example.com/socket"
}
```

### gRPC Provider

For connecting to gRPC services.

```json
{
  "name": "my_grpc_service",
  "provider_type": "grpc",
  "host": "grpc.example.com",
  "port": 50051,
  "service_name": "MyService",
  "method_name": "MyMethod",
  "use_ssl": true
}
```

### GraphQL Provider

For interacting with GraphQL APIs. The `url` should point to the discovery endpoint.

```json
{
  "name": "my_graphql_api",
  "provider_type": "graphql",
  "url": "https://api.example.com/utcp",
  "operation_type": "query"
}
```

### TCP Provider

For raw TCP socket communication.

```json
{
  "name": "raw_tcp_service",
  "provider_type": "tcp",
  "host": "localhost",
  "port": 12345
}
```

### UDP Provider

For UDP socket communication.

```json
{
  "name": "udp_telemetry_service",
  "provider_type": "udp",
  "host": "localhost",
  "port": 54321
}
```

### WebRTC Provider

For peer-to-peer communication using WebRTC.

```json
{
  "name": "p2p_data_transfer",
  "provider_type": "webrtc",
  "signaling_server": "wss://signaling.example.com",
  "peer_id": "unique-peer-id"
}
```

### MCP Provider

For interoperability with Model Context Protocol (MCP) servers.

```json
{
  "name": "my_mcp_server",
  "provider_type": "mcp",
  "config": {
    "mcpServers": {
      "server_one": {
        "command": "python",
        "args": ["-m", "my_mcp_server.main"]
      }
    }
  }
}
```

### Text Provider

For loading tool definitions from a local file. This is useful for defining a collection of tools from different providers in a single place.

```json
{
  "name": "my_local_tools",
  "provider_type": "text",
  "file_path": "/path/to/my/tools.json"
}
```

### Authentication

UTCP supports several authentication methods, which can be configured on a per-provider basis:

*   **API Key**: `ApiKeyAuth` - Authentication using an API key sent in a header.
*   **Basic Auth**: `BasicAuth` - Authentication using a username and password.
*   **OAuth2**: `OAuth2Auth` - Authentication using the OAuth2 protocol.

## UTCP Client

A UTCP client is responsible for:

1.  **Registering Tool Providers**: The client registers tool providers from a configuration, typically a JSON file containing a list of `Provider` objects. The client parses this list and calls `register_tool_provider` for each one. During this process, the client connects to the provider's discovery endpoint, retrieves its list of tools, and makes them available for use.
2.  **Calling Tools**: When a tool is called, the client uses the information in the tool's `provider` object to make the request, handling the specific communication protocol and any required authentication.
3.  **Deregistering Tool Providers**: The client can disconnect from a provider, removing its tools from the available list.

Tool names are namespaced with their provider's name (e.g., `my_api.get_weather`) to avoid conflicts.

## Build
1. Create a virtual environment (e.g. `conda create --name utcp python=3.10`) and enable it (`conda activate utcp`)
2. Install required libraries (`pip install -r requirements.txt`)
3. `python -m pip install --upgrade pip`
4. `python -m build`
5. `pip install dist/utcp-<version>.tar.gz` (e.g. `pip install dist/utcp-1.0.0.tar.gz`)
