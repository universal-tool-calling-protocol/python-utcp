# UTCP WebSocket Plugin

WebSocket communication protocol plugin for UTCP, enabling real-time bidirectional communication with tool providers.

## Features

- ✅ **Real-time Communication**: Bidirectional WebSocket connections for live data exchange
- ✅ **Multiple Authentication**: API Key, Basic Auth, and OAuth2 support
- ✅ **Flexible Message Formats**: JSON and text-based templates
- ✅ **Connection Management**: Keep-alive, reconnection, and connection pooling
- ✅ **Streaming Support**: Both single-response and streaming tool execution
- ✅ **Security Enforced**: WSS required (or ws://localhost for development)
- ✅ **Tool Discovery**: Automatic tool discovery via WebSocket handshake

## Installation

```bash
pip install utcp-websocket
```

For development:

```bash
pip install -e plugins/communication_protocols/websocket
```

## Quick Start

### Basic Configuration

```python
from utcp.utcp_client import UtcpClient

client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "realtime_service",
        "call_template_type": "websocket",
        "url": "wss://api.example.com/ws"
    }]
})

# Call a tool
result = await client.call_tool("realtime_service.get_data", {"id": "123"})
```

### With Authentication

```python
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "secure_ws",
        "call_template_type": "websocket",
        "url": "wss://api.example.com/ws",
        "auth": {
            "auth_type": "api_key",
            "api_key": "${WS_API_KEY}",
            "var_name": "Authorization",
            "location": "header"
        },
        "keep_alive": True,
        "protocol": "utcp-v1"
    }]
})
```

## Configuration Options

### WebSocketCallTemplate Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `call_template_type` | string | Yes | `"websocket"` | Must be "websocket" |
| `url` | string | Yes | - | WebSocket URL (wss:// or ws://localhost) |
| `protocol` | string | No | `null` | WebSocket subprotocol |
| `keep_alive` | boolean | No | `true` | Enable persistent connection with heartbeat |
| `request_data_format` | string | No | `"json"` | Format for messages ("json" or "text") |
| `request_data_template` | string | No | `null` | Template for text format |
| `timeout` | integer | No | `30` | Timeout in seconds |
| `headers` | object | No | `null` | Static headers for handshake |
| `header_fields` | array | No | `null` | Tool arguments to map to headers |
| `auth` | object | No | `null` | Authentication configuration |

## Message Formats

### JSON Format (Default)

Tool call message:
```json
{
  "type": "call_tool",
  "request_id": "unique_id",
  "tool_name": "tool_name",
  "arguments": {"arg1": "value1"}
}
```

Expected response:
```json
{
  "type": "tool_response",
  "request_id": "unique_id",
  "result": {"data": "value"}
}
```

### Text Format with Template

Configuration:
```python
{
    "call_template_type": "websocket",
    "url": "wss://api.example.com/ws",
    "request_data_format": "text",
    "request_data_template": "CMD:UTCP_ARG_command_UTCP_ARG;DATA:UTCP_ARG_data_UTCP_ARG"
}
```

This sends: `CMD:my_command;DATA:my_data`

## Authentication

### API Key Authentication

```python
{
    "auth": {
        "auth_type": "api_key",
        "api_key": "${API_KEY}",
        "var_name": "Authorization",
        "location": "header"
    }
}
```

### Basic Authentication

```python
{
    "auth": {
        "auth_type": "basic",
        "username": "${USERNAME}",
        "password": "${PASSWORD}"
    }
}
```

### OAuth2 Authentication

```python
{
    "auth": {
        "auth_type": "oauth2",
        "client_id": "${CLIENT_ID}",
        "client_secret": "${CLIENT_SECRET}",
        "token_url": "https://auth.example.com/token",
        "scope": "read write"
    }
}
```

## Tool Discovery Protocol

The WebSocket plugin uses the UTCP discovery protocol:

1. **Client sends discovery request:**
```json
{"type": "utcp"}
```

2. **Server responds with UtcpManual:**
```json
{
    "manual_version": "1.0.0",
    "utcp_version": "1.0.1",
    "tools": [
        {
            "name": "get_data",
            "description": "Get data by ID",
            "inputs": {...},
            "outputs": {...},
            "tool_call_template": {
                "call_template_type": "websocket",
                "url": "wss://api.example.com/ws"
            }
        }
    ]
}
```

## Examples

### Real-time Data Subscription

```python
{
    "name": "stock_updates",
    "call_template_type": "websocket",
    "url": "wss://api.stocks.com/ws",
    "auth": {
        "auth_type": "api_key",
        "api_key": "${STOCK_API_KEY}",
        "var_name": "X-API-Key",
        "location": "header"
    },
    "keep_alive": True,
    "timeout": 60
}
```

### IoT Device Control

```python
{
    "name": "iot_devices",
    "call_template_type": "websocket",
    "url": "wss://iot.example.com/ws",
    "request_data_format": "text",
    "request_data_template": "DEVICE:UTCP_ARG_device_id_UTCP_ARG CMD:UTCP_ARG_command_UTCP_ARG",
    "timeout": 10
}
```

### Chat Bot Integration

```python
{
    "name": "chatbot",
    "call_template_type": "websocket",
    "url": "wss://chat.example.com/ws",
    "protocol": "chat-v1",
    "keep_alive": True,
    "auth": {
        "auth_type": "api_key",
        "api_key": "Bearer ${CHAT_TOKEN}",
        "var_name": "Authorization",
        "location": "header"
    }
}
```

## Streaming Responses

The WebSocket plugin supports streaming tool execution:

```python
async for chunk in client.call_tool_streaming("service.stream_data", {"query": "test"}):
    print(chunk)
```

Server sends multiple responses:
```json
{"type": "tool_response", "request_id": "...", "result": {"chunk": 1}}
{"type": "tool_response", "request_id": "...", "result": {"chunk": 2}}
{"type": "stream_end", "request_id": "..."}
```

## Security

- **WSS Required**: Production URLs must use `wss://` for encrypted communication
- **Localhost Exception**: `ws://localhost` and `ws://127.0.0.1` allowed for development
- **Authentication**: Full support for API Key, Basic Auth, and OAuth2
- **Token Caching**: OAuth2 tokens are cached and automatically refreshed

## Error Handling

Tool errors are communicated via error responses:

```json
{
    "type": "tool_error",
    "request_id": "unique_id",
    "error": "Error message"
}
```

Python exception handling:
```python
try:
    result = await client.call_tool("service.tool", {"arg": "value"})
except RuntimeError as e:
    print(f"Tool call failed: {e}")
except asyncio.TimeoutError:
    print("Tool call timed out")
```

## Best Practices

1. **Use WSS in Production**: Always use `wss://` for secure connections
2. **Set Appropriate Timeouts**: Configure timeouts based on expected response times
3. **Enable Keep-Alive**: Use `keep_alive: true` for persistent connections
4. **Handle Errors Gracefully**: Implement proper error handling for network issues
5. **Monitor Connections**: Track connection health and implement reconnection logic
6. **Use Subprotocols**: Specify WebSocket subprotocols when needed for compatibility

## Comparison with Other Protocols

| Feature | WebSocket | HTTP | SSE |
|---------|-----------|------|-----|
| Bidirectional | ✅ | ❌ | ❌ |
| Real-time | ✅ | ❌ | ✅ |
| Persistent | ✅ | ❌ | ✅ |
| Overhead | Low | High | Medium |
| Complexity | Medium | Low | Low |

## Testing

Run tests for the WebSocket plugin:

```bash
pytest plugins/communication_protocols/websocket/tests/ -v
```

With coverage:

```bash
pytest plugins/communication_protocols/websocket/tests/ --cov=utcp_websocket --cov-report=term-missing
```

## Contributing

Contributions are welcome! Please see the [main repository](https://github.com/universal-tool-calling-protocol/python-utcp) for contribution guidelines.

## License

Mozilla Public License 2.0 (MPL-2.0)
