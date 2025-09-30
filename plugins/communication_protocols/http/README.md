# UTCP HTTP Plugin

[![PyPI Downloads](https://static.pepy.tech/badge/utcp-http)](https://pepy.tech/projects/utcp-http)

HTTP communication protocol plugin for UTCP, supporting REST APIs, Server-Sent Events (SSE), and streaming HTTP.

## Features

- **HTTP/REST APIs**: Full support for GET, POST, PUT, DELETE, PATCH methods
- **Authentication**: API key, Basic Auth, OAuth2 support
- **Server-Sent Events (SSE)**: Real-time event streaming
- **Streaming HTTP**: Large response handling with chunked transfer
- **OpenAPI Integration**: Automatic tool generation from OpenAPI specs
- **Path Parameters**: URL templating with `{parameter}` syntax
- **Custom Headers**: Static and dynamic header support

## Installation

```bash
pip install utcp-http
```

## Quick Start

```python
from utcp.utcp_client import UtcpClient

# Basic HTTP API
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "api_service",
        "call_template_type": "http",
        "url": "https://api.example.com/users/{user_id}",
        "http_method": "GET"
    }]
})

result = await client.call_tool("api_service.get_user", {"user_id": "123"})
```

## Configuration Examples

### Basic HTTP Request
```json
{
  "name": "my_api",
  "call_template_type": "http",
  "url": "https://api.example.com/data",
  "http_method": "GET"
}
```

### With API Key Authentication
```json
{
  "name": "secure_api",
  "call_template_type": "http",
  "url": "https://api.example.com/data",
  "http_method": "POST",
  "auth": {
    "auth_type": "api_key",
    "api_key": "${API_KEY}",
    "var_name": "X-API-Key",
    "location": "header"
  }
}
```

### OAuth2 Authentication
```json
{
  "name": "oauth_api",
  "call_template_type": "http",
  "url": "https://api.example.com/data",
  "auth": {
    "auth_type": "oauth2",
    "client_id": "${CLIENT_ID}",
    "client_secret": "${CLIENT_SECRET}",
    "token_url": "https://auth.example.com/token"
  }
}
```

### Server-Sent Events (SSE)
```json
{
  "name": "event_stream",
  "call_template_type": "sse",
  "url": "https://api.example.com/events",
  "event_type": "message",
  "reconnect": true
}
```

### Streaming HTTP
```json
{
  "name": "large_data",
  "call_template_type": "streamable_http",
  "url": "https://api.example.com/download",
  "chunk_size": 8192
}
```

## OpenAPI Integration

Automatically generate UTCP tools from OpenAPI specifications:

```python
from utcp_http.openapi_converter import OpenApiConverter

converter = OpenApiConverter()
manual = await converter.convert_openapi_to_manual(
    "https://api.example.com/openapi.json"
)

client = await UtcpClient.create()
await client.register_manual(manual)
```

## Error Handling

```python
from utcp.exceptions import ToolCallError
import httpx

try:
    result = await client.call_tool("api.get_data", {"id": "123"})
except ToolCallError as e:
    if isinstance(e.__cause__, httpx.HTTPStatusError):
        print(f"HTTP {e.__cause__.response.status_code}: {e.__cause__.response.text}")
```

## Related Documentation

- [Main UTCP Documentation](../../../README.md)
- [Core Package Documentation](../../../core/README.md)
- [CLI Plugin](../cli/README.md)
- [MCP Plugin](../mcp/README.md)
- [Text Plugin](../text/README.md)

## Examples

For complete examples, see the [UTCP examples repository](https://github.com/universal-tool-calling-protocol/utcp-examples).
