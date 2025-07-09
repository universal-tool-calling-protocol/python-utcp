# Universal Tool Calling Protocol (UTCP)

## Introduction

The Universal Tool Calling Protocol (UTCP) is a modern, flexible, and scalable standard for defining and interacting with tools across a wide variety of communication protocols. It is designed to be easy to use, interoperable, and extensible, making it a powerful choice for building and consuming tool-based services.

In contrast to other protocols like MCP, UTCP places a strong emphasis on:

*   **Scalability**: UTCP is designed to handle a large number of tools and providers without compromising performance.
*   **Interoperability**: With support for a wide range of provider types (including HTTP, WebSockets, gRPC, and even CLI tools), UTCP can integrate with almost any existing service or infrastructure.
*   **Ease of Use**: The protocol is built on simple, well-defined Pydantic models, making it easy for developers to implement and use.

## Usage Examples

These examples illustrate the core concepts of the UTCP client and server. They are not designed to be a single, runnable example.

> **Note:** For complete, end-to-end runnable examples, please refer to the `examples/` directory in this repository.

### 1. Using the UTCP Client

Setting up a client is simple. You point it to a `providers.json` file, and it handles the rest.

**`providers.json`**

This file tells the client where to find one or more UTCP Manuals (providers which return a list of tools).

```json
[
  {
    "name": "cool_public_apis",
    "provider_type": "http",
    "url": "http://utcp.io/public-apis-manual",
    "http_method": "GET"
  }
]
```

**`client.py`**

This script initializes the client and calls a tool from the provider defined above.

```python
import asyncio
from utcp.client import UtcpClient

async def main():
    # Create a client instance. It automatically loads providers
    # from the specified file path.
    client = await UtcpClient.create(
        config={"providers_file_path": "./providers.json"}
    )

    # Call a tool. The name is namespaced: `provider_name.tool_name`
    result = await client.call_tool(
        tool_name="cool_public_apis.example_tool", 
        arguments={}
    )

    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Providing a UTCP Manual

Any type of server or service can be exposed as a UTCP tool. The only requirement is that a `UTCPManual` is provided to the client. This manual can be served by the tool itself or, more powerfully, by a third-party registry. This allows for wrapping existing APIs and services that are not natively UTCP-aware.

Here is a minimal example using FastAPI to serve a `UTCPManual` for a tool:

**`server.py`**
```python
from fastapi import FastAPI

app = FastAPI()

# The discovery endpoint returns the tool manual
@app.get("/utcp")
def utcp_discovery():
    return {
        "version": "1.0",
        "tools": [
            {
                "name": "get_weather",
                "description": "Get current weather for a location",
                "inputs": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"}
                    }
                },
                "outputs": {
                    "type": "object",
                    "properties": {
                        "temperature": {"type": "number"}
                    }
                },
                "provider": {
                    "provider_type": "http",
                    "url": "https://example.com/api/weather",
                    "http_method": "GET"
                }
            }
        ]
    }

# The actual tool endpoint
@app.get("/api/weather")
def get_weather(location: str):
    return {"temperature": 22.5, "conditions": "Sunny"}
```

## Protocol Specification

UTCP is defined by a set of core data models that describe tools, how to connect to them (providers), and how to secure them (authentication).

### Tool Discovery

For a client to use a tool, it must be provided with a `UtcpManual` object. This manual contains a list of all the tools available from a provider. Depending on the provider type, this manual might be retrieved from a discovery endpoint (like an HTTP URL) or loaded from a local source (like a file for a CLI tool).

#### `UtcpManual` Model

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

### Authentication

UTCP supports several authentication methods to secure tool access. The `auth` object within a provider's configuration specifies the authentication method to use.

#### API Key (`ApiKeyAuth`)

Authentication using a static API key, typically sent in a request header.

```json
{
  "auth_type": "api_key",
  "api_key": "YOUR_SECRET_API_KEY",
  "var_name": "X-API-Key"
}
```

#### Basic Auth (`BasicAuth`)

Authentication using a username and password.

```json
{
  "auth_type": "basic",
  "username": "your_username",
  "password": "your_password"
}
```

#### OAuth2 (`OAuth2Auth`)

Authentication using the OAuth2 client credentials flow. The UTCP client will automatically fetch a bearer token from the `token_url` and use it for subsequent requests.

```json
{
  "auth_type": "oauth2",
  "token_url": "https://auth.example.com/token",
  "client_id": "your_client_id",
  "client_secret": "your_client_secret",
  "scope": "read write"
}
```

### Providers

Providers are at the heart of UTCP's flexibility. They define the communication protocol for a given tool. UTCP supports a wide range of provider types:

*   `http`: RESTful HTTP/HTTPS API
*   `sse`: Server-Sent Events
*   `http_stream`: HTTP Chunked Transfer Encoding
*   `cli`: Command Line Interface
*   `websocket`: WebSocket bidirectional connection (work in progress)
*   `grpc`: gRPC (Google Remote Procedure Call) (work in progress)
*   `graphql`: GraphQL query language (work in progress)
*   `tcp`: Raw TCP socket (work in progress)
*   `udp`: User Datagram Protocol (work in progress)
*   `webrtc`: Web Real-Time Communication (work in progress)
*   `mcp`: Model Context Protocol (for interoperability)
*   `text`: Local text file

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
    "auth_type": "oauth2",
    "token_url": "https://api.example.com/oauth/token",
    "client_id": "your_client_id",
    "client_secret": "your_client_secret"
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

### WebSocket Provider (work in progress)

For tools that communicate over a WebSocket connection. Tool discovery may need to be handled via a separate HTTP endpoint.

```json
{
  "name": "realtime_chat_service",
  "provider_type": "websocket",
  "url": "wss://api.example.com/socket"
}
```

### gRPC Provider (work in progress)

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

### GraphQL Provider (work in progress)

For interacting with GraphQL APIs. The `url` should point to the discovery endpoint.

```json
{
  "name": "my_graphql_api",
  "provider_type": "graphql",
  "url": "https://api.example.com/utcp",
  "operation_type": "query"
}
```

### TCP Provider (work in progress)

For raw TCP socket communication.

```json
{
  "name": "raw_tcp_service",
  "provider_type": "tcp",
  "host": "localhost",
  "port": 12345
}
```

### UDP Provider (work in progress)

For UDP socket communication.

```json
{
  "name": "udp_telemetry_service",
  "provider_type": "udp",
  "host": "localhost",
  "port": 54321
}
```

### WebRTC Provider (work in progress)

For peer-to-peer communication using WebRTC.

```json
{
  "name": "p2p_data_transfer",
  "provider_type": "webrtc",
  "signaling_server": "https://signaling.example.com",
  "peer_id": "remote-peer-id"
}
```

### MCP Provider

For interoperability with the Model Context Protocol (MCP). This provider can connect to MCP servers via `stdio` or `http`.

```json
{
  "name": "my_mcp_service",
  "provider_type": "mcp",
  "config": {
    "mcpServers": {
      "my-server": {
        "transport": "http",
        "url": "http://localhost:8000/mcp"
      }
    }
  },
  "auth": {
    "auth_type": "oauth2",
    "token_url": "http://localhost:8000/token",
    "client_id": "test-client",
    "client_secret": "test-secret"
  }
}
```

### Text Provider

For loading tool definitions from a local text file. This is useful for defining a collection of tools that may use various other providers.

```json
{
  "name": "my_local_tools",
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

## UTCP Client Architecture

The Python UTCP client provides a robust and extensible framework for interacting with tool providers. Its architecture is designed around a few key components that work together to manage, execute, and search for tools.

### Core Components

*   **`UtcpClient`**: The main entry point for interacting with the UTCP ecosystem. It orchestrates the registration of providers, the execution of tools, and the search for available tools.
*   **`UtcpClientConfig`**: A Pydantic model that defines the client's configuration. It specifies the path to the providers' configuration file (`providers_file_path`) and how to load sensitive variables (e.g., from a `.env` file using `load_variables_from`).
*   **`ClientTransportInterface`**: An abstract base class that defines the contract for all transport implementations (e.g., `HttpClientTransport`, `CliTransport`). Each transport is responsible for the protocol-specific communication required to register and call tools.
*   **`ToolRepository`**: An abstract base class that defines the interface for storing and retrieving tools and providers. The default implementation is `InMemToolRepository`, which stores everything in memory.
*   **`ToolSearchStrategy`**: An abstract base class for implementing different tool search algorithms. The default is `TagSearchStrategy`, which scores tools based on matching tags and keywords from the tool's description.

### Initialization and Configuration

A `UtcpClient` instance is created using the asynchronous `UtcpClient.create()` class method. This method initializes the client with a configuration, a tool repository, and a search strategy.

```python
import asyncio
from utcp.client import UtcpClient

async def main():
    # The client automatically loads providers from the path specified in the config
    client = await UtcpClient.create(
        config={
            "providers_file_path": "/path/to/your/providers.json",
            "load_variables_from": [{
                "type": "dotenv",
                "env_file_path": ".env"
            }]
        }
    )
    # ... use the client

asyncio.run(main())
```

During initialization, the client reads the `providers.json` file, substitutes any variables (e.g., `${API_KEY}`), and registers each provider.

### Tool Management and Execution

- **Registration**: The `register_tool_provider` method uses the appropriate transport to fetch the tool definitions from a provider and saves them in the `ToolRepository`.
- **Execution**: The `call_tool` method finds the requested tool in the repository, retrieves its provider information, and uses the correct transport to execute the call with the given arguments. Tool names are namespaced by their provider (e.g., `my_api.get_weather`).
- **Deregistration**: Providers can be deregistered, which removes them and their associated tools from the repository.

### Tool Search

The `search_tools` method allows you to find relevant tools based on a query. It delegates the search to the configured `ToolSearchStrategy`.

```python
tools = client.search_tools(query="get current weather in London")
for tool in tools:
    print(tool.name, tool.description)
```

## Build
1. Create a virtual environment (e.g. `conda create --name utcp python=3.10`) and enable it (`conda activate utcp`)
2. Install required libraries (`pip install -r requirements.txt`)
3. `python -m pip install --upgrade pip`
4. `python -m build`
5. `pip install dist/utcp-<version>.tar.gz` (e.g. `pip install dist/utcp-1.0.0.tar.gz`)

# Contributors

## Main contributors
- Razvan-Ion Radulescu (razvan.radulescu@bevel.software, www.bevel.software)
- Andrei-Stefan Ghiurtu (https://www.linkedin.com/in/andrei-stefan-ghiurtu/)

## Distribution Team
- Juan Viera Garcia (juan@bevel.software, www.bevel.software)
- Ali Raza (ali.raza@bevel.software, www.bevel.software)