# LLM Guide: Creating UTCP Manuals from API Specifications

## 1. Objective

Your task is to analyze a given API specification (e.g., OpenAPI/Swagger, or plain text documentation) and convert it into a `UTCPManual` JSON object. This manual allows a UTCP client to understand and interact with the API's tools.

## 2. Core Concepts

-   **`UTCPManual`**: The root JSON object that contains a list of all available tools from a provider. It has two main keys: `version` and `tools`.
-   **`Tool`**: A JSON object representing a single function or API endpoint. It describes what the tool does, what inputs it needs, what it returns, and how to call it.
-   **`Provider`**: A JSON object *inside* a `Tool` that contains the specific connection details (e.g., HTTP URL, method, etc.).

## 3. Step-by-Step Conversion Process

Follow these steps to transform an API endpoint into a UTCP `Tool`.

### Step 1: Identify Individual API Endpoints

Scan the API documentation and treat each unique API endpoint as a separate tool. For a REST API, an endpoint is a unique combination of an HTTP method and a URL path (e.g., `GET /users/{id}` is one tool, and `POST /users` is another).

### Step 2: For Each Endpoint, Create a `Tool` Object

For every endpoint you identify, you will create one JSON object that will be added to the `tools` array in the final `UTCPManual`.

### Step 3: Map API Details to `Tool` Fields

This is the core of the task. Populate the fields of the `Tool` object as follows:

-   **`name`**: (String) Create a short, descriptive, `snake_case` name for the tool. Example: `get_user_by_id`.
-   **`description`**: (String) Use the summary or description from the API documentation to explain what the tool does.
-   **`tags`**: (Array of Strings) Add relevant keywords that can be used to search for this tool. These could be derived from the API's own tags or categories. Example: `["users", "profile", "read"]`.
-   **`average_response_size`**: (Integer, Optional) If the API documentation provides information on the typical size of the response payload in bytes, include it here. This is useful for performance considerations.
-   **`inputs`**: (Object) A JSON Schema object describing all the parameters the API endpoint accepts (path, query, headers, and body).
    -   Set `type` to `"object"`.
    -   In `properties`, create a key for *each* parameter. The value should be an object defining its `type` (e.g., `"string"`, `"number"`) and `description`.
    -   In `required`, create an array listing the names of all mandatory parameters.
-   **`outputs`**: (Object) A JSON Schema object describing the successful response from the API (e.g., the `200 OK` response body).
    -   Set `type` to `"object"`.
    -   In `properties`, map the fields of the JSON response body.
-   **`provider`**: (Object) This object contains the technical details needed to make the actual API call.
    -   `provider_type`: (String) Almost always `"http"` for web APIs.
    -   `url`: (String) The full URL of the endpoint. Use curly braces for path parameters, e.g., `https://api.example.com/users/{id}`.
    -   `http_method`: (String) The HTTP method, e.g., `"GET"`, `"POST"`.
    -   `content_type`: (String) The request's content type, typically `"application/json"`.
    -   `path_fields`: (Array of Strings) List the names of any parameters that are part of the URL path.
    -   `query_fields`: (Array of Strings) List the names of any parameters sent as URL query strings.
    -   `header_fields`: (Array of Strings) List the names of any parameters sent as request headers.
    -   `body_field`: (String) If the request has a JSON body, specify the name of the single input property that contains the body object.
    -   `auth`: (Object, Optional) If the API requires authentication, add this object. The `auth_type` field determines the authentication method (`api_key`, `basic`, or `oauth2`). Populate the other fields based on the API's security scheme. See the `auth.py` reference below for the exact structure.

### Step 4: Assemble the Final `UTCPManual`

Once you have created a `Tool` object for every endpoint, assemble them into the final `UTCPManual`.

1.  Create the root JSON object.
2.  Set the `version` key to `"1.0"`.
3.  Create a `tools` key with an array containing all the `Tool` objects you generated.

## 4. Example

## 5. Data Model Reference

Below are the core Pydantic models that define the structure of a `UTCPManual`. Use these as the ground truth for the JSON structure you need to generate.

### `tool.py`

```python
import inspect
from typing import Dict, Any, Optional, List, Literal, Union, get_type_hints
from pydantic import BaseModel, Field, TypeAdapter
from utcp.shared.provider import (
    HttpProvider,
    CliProvider,
    WebSocketProvider,
    GRPCProvider,
    GraphQLProvider,
    TCPProvider,
    UDPProvider,
    StreamableHttpProvider,
    SSEProvider,
    WebRTCProvider,
    MCPProvider,
    TextProvider,
)

class ToolInputOutputSchema(BaseModel):
    type: str = Field(default="object")
    properties: Dict[str, Any] = Field(default_factory=dict)
    required: Optional[List[str]] = None
    description: Optional[str] = None
    title: Optional[str] = None

class Tool(BaseModel):
    name: str
    description: str = ""
    inputs: ToolInputOutputSchema = Field(default_factory=ToolInputOutputSchema)
    outputs: ToolInputOutputSchema = Field(default_factory=ToolInputOutputSchema)
    tags: List[str] = []
    average_response_size: Optional[int] = None
    provider: Optional[Union[
        HttpProvider,
        CliProvider,
        WebSocketProvider,
        GRPCProvider,
        GraphQLProvider,
        TCPProvider,
        UDPProvider,
        StreamableHttpProvider,
        SSEProvider,
        WebRTCProvider,
        MCPProvider,
        TextProvider,
    ]] = None
```

### `auth.py`

```python
from typing import Literal, Optional, TypeAlias, Union

from pydantic import BaseModel, Field

class ApiKeyAuth(BaseModel):
    """Authentication using an API key.

    The key can be provided directly or sourced from an environment variable.
    """

    auth_type: Literal["api_key"] = "api_key"
    api_key: str = Field(..., description="The API key for authentication.")
    var_name: str = Field(
        ..., description="The name of the variable containing the API key."
    )


class BasicAuth(BaseModel):
    """Authentication using a username and password."""

    auth_type: Literal["basic"] = "basic"
    username: str = Field(..., description="The username for basic authentication.")
    password: str = Field(..., description="The password for basic authentication.")


class OAuth2Auth(BaseModel):
    """Authentication using OAuth2."""

    auth_type: Literal["oauth2"] = "oauth2"
    token_url: str = Field(..., description="The URL to fetch the OAuth2 token from.")
    client_id: str = Field(..., description="The OAuth2 client ID.")
    client_secret: str = Field(..., description="The OAuth2 client secret.")
    scope: Optional[str] = Field(None, description="The OAuth2 scope.")


Auth: TypeAlias = Union[ApiKeyAuth, BasicAuth, OAuth2Auth]
```

### `provider.py`

```python
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
    'text', # Text file provider
]

class Provider(BaseModel):
    name: str
    provider_type: ProviderType
    startup_command: Optional[List[str]] = None  # For launching the provider if needed

class HttpProvider(Provider):
    """Options specific to HTTP tools"""

    provider_type: Literal["http"] = "http"
    http_method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = "GET"
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
```

**API Specification Snippet:**

```
Endpoint: GET /v1/weather
Description: Retrieves the current weather for a specific city.

Query Parameters:
- `city` (string, required): The name of the city (e.g., "London").
- `units` (string, optional): The temperature units. Can be 'metric' or 'imperial'. Defaults to 'metric'.

Response (200 OK):
{
  "temperature": 15,
  "conditions": "Cloudy",
  "humidity": 82
}
```

**Generated `UTCPManual`:**

```json
{
  "version": "1.0",
  "tools": [
    {
      "name": "get_weather",
      "description": "Retrieves the current weather for a specific city.",
      "inputs": {
        "type": "object",
        "properties": {
          "city": {
            "type": "string",
            "description": "The name of the city (e.g., \"London\")."
          },
          "units": {
            "type": "string",
            "description": "The temperature units. Can be 'metric' or 'imperial'."
          }
        },
        "required": [
          "city"
        ]
      },
      "outputs": {
        "type": "object",
        "properties": {
          "temperature": {
            "type": "number"
          },
          "conditions": {
            "type": "string"
          },
          "humidity": {
            "type": "number"
          }
        }
      },
      "provider": {
        "provider_type": "http",
        "url": "https://api.example.com/v1/weather",
        "http_method": "GET",
        "content_type": "application/json",
        "query_fields": [
          "city",
          "units"
        ]
      }
    }
  ]
}
```
