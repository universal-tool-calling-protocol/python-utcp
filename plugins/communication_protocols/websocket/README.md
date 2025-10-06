# UTCP WebSocket Plugin

WebSocket communication protocol plugin for UTCP, enabling real-time bidirectional communication with **maximum flexibility** to support ANY WebSocket endpoint format.

## Key Feature: Maximum Flexibility

**The WebSocket plugin is designed to work with ANY existing WebSocket endpoint without modification.**

Unlike other implementations that enforce specific message structures, this plugin:
- ✅ **No enforced request format**: Use `message` templates with `UTCP_ARG_arg_name_UTCP_ARG` placeholders
- ✅ **No enforced response format**: Returns raw responses by default
- ✅ **Works with existing endpoints**: No need to modify your WebSocket servers
- ✅ **Flexible templating**: Support dict or string message templates

This addresses the UTCP principle: "Talk to as many WebSocket endpoints as possible."

## Features

- ✅ **Maximum Flexibility**: Works with ANY WebSocket endpoint without modification
- ✅ **Flexible Message Templates**: Dict or string templates with `UTCP_ARG_arg_name_UTCP_ARG` placeholders
- ✅ **No Enforced Structure**: Send/receive messages in any format
- ✅ **Real-time Communication**: Bidirectional WebSocket connections
- ✅ **Multiple Authentication**: API Key, Basic Auth, and OAuth2 support
- ✅ **Connection Management**: Keep-alive, reconnection, and connection pooling
- ✅ **Streaming Support**: Both single-response and streaming execution
- ✅ **Security Enforced**: WSS required (or ws://localhost for development)

## Installation

```bash
pip install utcp-websocket
```

For development:

```bash
pip install -e plugins/communication_protocols/websocket
```

## Quick Start

### Basic Usage (No Template - Maximum Flexibility)

```python
from utcp.utcp_client import UtcpClient

# Works with ANY WebSocket endpoint - just sends arguments as JSON
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "my_websocket",
        "call_template_type": "websocket",
        "url": "wss://api.example.com/ws"
    }]
})

# Sends: {"user_id": "123", "action": "getData"}
result = await client.call_tool("my_websocket.get_data", {
    "user_id": "123",
    "action": "getData"
})
```

### With Message Template (Dict)

```python
{
    "name": "formatted_ws",
    "call_template_type": "websocket",
    "url": "wss://api.example.com/ws",
    "message": {
        "type": "request",
        "action": "UTCP_ARG_action_UTCP_ARG",
        "params": {
            "user_id": "UTCP_ARG_user_id_UTCP_ARG",
            "query": "UTCP_ARG_query_UTCP_ARG"
        }
    }
}
```

Calling with `{"action": "search", "user_id": "123", "query": "test"}` sends:
```json
{
  "type": "request",
  "action": "search",
  "params": {
    "user_id": "123",
    "query": "test"
  }
}
```

### With Message Template (String)

```python
{
    "name": "text_ws",
    "call_template_type": "websocket",
    "url": "wss://iot.example.com/ws",
    "message": "CMD:UTCP_ARG_command_UTCP_ARG;DEVICE:UTCP_ARG_device_id_UTCP_ARG;VALUE:UTCP_ARG_value_UTCP_ARG"
}
```

Calling with `{"command": "SET_TEMP", "device_id": "dev123", "value": "25"}` sends:
```
CMD:SET_TEMP;DEVICE:dev123;VALUE:25
```

## Configuration Options

### WebSocketCallTemplate Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `call_template_type` | string | Yes | `"websocket"` | Must be "websocket" |
| `url` | string | Yes | - | WebSocket URL (wss:// or ws://localhost) |
| `message` | string\|dict | No | `null` | Message template with UTCP_ARG_arg_name_UTCP_ARG placeholders |
| `response_format` | string | No | `null` | Expected response format ("json", "text", "raw") |
| `protocol` | string | No | `null` | WebSocket subprotocol |
| `keep_alive` | boolean | No | `true` | Enable persistent connection with heartbeat |
| `timeout` | integer | No | `30` | Timeout in seconds |
| `headers` | object | No | `null` | Static headers for handshake |
| `header_fields` | array | No | `null` | Tool arguments to map to headers |
| `auth` | object | No | `null` | Authentication configuration |

## Message Templating

### No Template (Default - Maximum Flexibility)

If `message` is not specified, arguments are sent as-is in JSON format:

```python
# Config
{"call_template_type": "websocket", "url": "wss://api.example.com/ws"}

# Call
await client.call_tool("ws.tool", {"foo": "bar", "baz": 123})

# Sends exactly:
{"foo": "bar", "baz": 123}
```

This works with **any** WebSocket endpoint that accepts JSON.

### Dict Template

Use dict templates for structured messages:

```python
{
    "message": {
        "jsonrpc": "2.0",
        "method": "UTCP_ARG_method_UTCP_ARG",
        "params": "UTCP_ARG_params_UTCP_ARG",
        "id": 1
    }
}
```

### String Template

Use string templates for text-based protocols:

```python
{
    "message": "GET UTCP_ARG_resource_UTCP_ARG HTTP/1.1\r\nHost: UTCP_ARG_host_UTCP_ARG\r\n\r\n"
}
```

### Nested Templates

Templates work recursively in dicts and lists:

```python
{
    "message": {
        "type": "command",
        "data": {
            "commands": ["UTCP_ARG_cmd1_UTCP_ARG", "UTCP_ARG_cmd2_UTCP_ARG"],
            "metadata": {
                "user": "UTCP_ARG_user_UTCP_ARG",
                "timestamp": "2025-01-01"
            }
        }
    }
}
```

## Response Handling

### No Format Specification (Default)

By default, responses are returned as-is (maximum flexibility):

```python
# Returns whatever the WebSocket sends - could be JSON string, text, or binary
result = await client.call_tool("ws.tool", {...})
```

### JSON Format

Parse responses as JSON:

```python
{
    "call_template_type": "websocket",
    "url": "wss://api.example.com/ws",
    "response_format": "json"
}
```

### Text Format

Return responses as text strings:

```python
{
    "response_format": "text"
}
```

### Raw Format

Return responses without any processing:

```python
{
    "response_format": "raw"
}
```

## Real-World Examples

### Example 1: Stock Price WebSocket (No Template)

Works with existing stock APIs without modification:

```python
{
    "name": "stocks",
    "call_template_type": "websocket",
    "url": "wss://stream.example.com/stocks",
    "auth": {
        "auth_type": "api_key",
        "api_key": "${STOCK_API_KEY}",
        "var_name": "Authorization",
        "location": "header"
    }
}

# Sends: {"symbol": "AAPL", "action": "subscribe"}
await client.call_tool("stocks.subscribe", {
    "symbol": "AAPL",
    "action": "subscribe"
})
```

### Example 2: IoT Device Control (String Template)

```python
{
    "name": "iot",
    "call_template_type": "websocket",
    "url": "wss://iot.example.com/devices",
    "message": "DEVICE:UTCP_ARG_device_id_UTCP_ARG CMD:UTCP_ARG_command_UTCP_ARG VAL:UTCP_ARG_value_UTCP_ARG"
}

# Sends: "DEVICE:light_01 CMD:SET_BRIGHTNESS VAL:75"
await client.call_tool("iot.control", {
    "device_id": "light_01",
    "command": "SET_BRIGHTNESS",
    "value": "75"
})
```

### Example 3: JSON-RPC WebSocket (Dict Template)

```python
{
    "name": "jsonrpc",
    "call_template_type": "websocket",
    "url": "wss://rpc.example.com/ws",
    "message": {
        "jsonrpc": "2.0",
        "method": "UTCP_ARG_method_UTCP_ARG",
        "params": "UTCP_ARG_params_UTCP_ARG",
        "id": 1
    },
    "response_format": "json"
}

# Sends: {"jsonrpc": "2.0", "method": "getUser", "params": {"id": 123}, "id": 1}
result = await client.call_tool("jsonrpc.call", {
    "method": "getUser",
    "params": {"id": 123}
})
```

### Example 4: Chat Application (Dict Template)

```python
{
    "name": "chat",
    "call_template_type": "websocket",
    "url": "wss://chat.example.com/ws",
    "message": {
        "type": "message",
        "channel": "UTCP_ARG_channel_UTCP_ARG",
        "user": "UTCP_ARG_user_UTCP_ARG",
        "text": "UTCP_ARG_text_UTCP_ARG",
        "timestamp": "{{now}}"
    }
}
```

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

## Streaming Responses

```python
async for chunk in client.call_tool_streaming("ws.stream", {"query": "data"}):
    print(chunk)
```

## Security

- **WSS Required**: Production URLs must use `wss://` for encrypted communication
- **Localhost Exception**: `ws://localhost` and `ws://127.0.0.1` allowed for development
- **Authentication**: Full support for API Key, Basic Auth, and OAuth2
- **Token Caching**: OAuth2 tokens are cached and automatically refreshed

## Best Practices

1. **Start Simple**: Don't use `message` template unless your endpoint requires specific format
2. **Use WSS in Production**: Always use `wss://` for secure connections
3. **Set Appropriate Timeouts**: Configure timeouts based on expected response times
4. **Test Without Template First**: Try without `message` template to see if it works
5. **Add Template Only When Needed**: Only add `message` template if endpoint requires specific structure

## Comparison with Enforced Formats

| Approach | Flexibility | Works with Existing Endpoints |
|----------|-------------|------------------------------|
| **UTCP WebSocket (This Plugin)** | ✅ Maximum | ✅ Yes - works with any endpoint |
| Enforced request/response structure | ❌ Limited | ❌ No - requires endpoint modification |
| UTCP-specific message format | ❌ Limited | ❌ No - only works with UTCP servers |

## Testing

Run tests:

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
