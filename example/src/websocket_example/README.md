# WebSocket Transport Example

This example demonstrates how to use the UTCP WebSocket transport for real-time communication.

## Overview

The WebSocket transport provides:
- Real-time bidirectional communication
- Tool discovery via WebSocket handshake
- Streaming tool execution
- Authentication support (API Key, Basic Auth, OAuth2)
- Automatic reconnection and keep-alive

## Files

- `websocket_server.py` - Mock WebSocket server implementing UTCP protocol
- `websocket_client.py` - Client example using WebSocket transport
- `providers.json` - WebSocket provider configuration

## Protocol

The UTCP WebSocket protocol uses JSON messages:

### Tool Discovery
```json
// Client sends:
{"type": "discover", "request_id": "unique_id"}

// Server responds:
{
  "type": "discovery_response", 
  "request_id": "unique_id",
  "tools": [...]
}
```

### Tool Execution
```json
// Client sends:
{
  "type": "call_tool",
  "request_id": "unique_id", 
  "tool_name": "tool_name",
  "arguments": {...}
}

// Server responds:
{
  "type": "tool_response",
  "request_id": "unique_id",
  "result": {...}
}
```

## Running the Example

1. Start the mock WebSocket server:
```bash
python websocket_server.py
```

2. In another terminal, run the client:
```bash
python websocket_client.py
```

## Configuration

The `providers.json` shows how to configure WebSocket providers with authentication:

```json
[
  {
    "name": "websocket_tools",
    "provider_type": "websocket",
    "url": "ws://localhost:8765/ws",
    "auth": {
      "auth_type": "api_key",
      "api_key": "your-api-key",
      "var_name": "X-API-Key",
      "location": "header"
    },
    "keep_alive": true,
    "protocol": "utcp-v1"
  }
]
```