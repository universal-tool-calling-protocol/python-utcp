# UTCP MCP Plugin

[![PyPI Downloads](https://static.pepy.tech/badge/utcp-mcp)](https://pepy.tech/projects/utcp-mcp)

Model Context Protocol (MCP) interoperability plugin for UTCP, enabling seamless integration with existing MCP servers.

## Features

- **MCP Server Integration**: Connect to existing MCP servers
- **Stdio Transport**: Local process-based MCP servers
- **HTTP Transport**: Remote MCP server connections
- **OAuth2 Authentication**: Secure authentication for HTTP servers
- **Migration Support**: Gradual migration from MCP to UTCP
- **Tool Discovery**: Automatic tool enumeration from MCP servers
- **Session Management**: Efficient connection handling

## Installation

```bash
pip install utcp-mcp
```

## Quick Start

```python
from utcp.utcp_client import UtcpClient

# Connect to MCP server
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "mcp_server",
        "call_template_type": "mcp",
        "config": {
            "mcpServers": {
                "filesystem": {
                    "command": "node",
                    "args": ["mcp-server.js"]
                }
            }
        }
    }]
})

# Call MCP tool through UTCP
result = await client.call_tool("mcp_server.filesystem.read_file", {
    "path": "/data/file.txt"
})
```

## Configuration Examples

### Stdio Transport (Local Process)
```json
{
  "name": "local_mcp",
  "call_template_type": "mcp",
  "config": {
    "mcpServers": {
      "filesystem": {
        "command": "python",
        "args": ["-m", "mcp_filesystem_server"],
        "env": {"LOG_LEVEL": "INFO"}
      }
    }
  }
}
```

### HTTP Transport (Remote Server)
```json
{
  "name": "remote_mcp",
  "call_template_type": "mcp",
  "config": {
    "mcpServers": {
      "api_server": {
        "transport": "http",
        "url": "https://mcp.example.com"
      }
    }
  }
}
```

### With OAuth2 Authentication
```json
{
  "name": "secure_mcp",
  "call_template_type": "mcp",
  "config": {
    "mcpServers": {
      "secure_server": {
        "transport": "http",
        "url": "https://mcp.example.com"
      }
    }
  },
  "auth": {
    "auth_type": "oauth2",
    "token_url": "https://auth.example.com/token",
    "client_id": "${CLIENT_ID}",
    "client_secret": "${CLIENT_SECRET}",
    "scope": "read:tools"
  }
}
```

### Multiple MCP Servers
```json
{
  "name": "multi_mcp",
  "call_template_type": "mcp",
  "config": {
    "mcpServers": {
      "filesystem": {
        "command": "python",
        "args": ["-m", "mcp_filesystem"]
      },
      "database": {
        "command": "node",
        "args": ["mcp-db-server.js"],
        "cwd": "/app/mcp-servers"
      }
    }
  }
}
```

## Migration Scenarios

### Gradual Migration from MCP to UTCP

**Phase 1: MCP Integration**
```python
# Use existing MCP servers through UTCP
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "legacy_mcp",
        "call_template_type": "mcp",
        "config": {"mcpServers": {"server": {...}}}
    }]
})
```

**Phase 2: Mixed Environment**
```python
# Mix MCP and native UTCP tools
client = await UtcpClient.create(config={
    "manual_call_templates": [
        {
            "name": "legacy_mcp",
            "call_template_type": "mcp",
            "config": {"mcpServers": {"old_server": {...}}}
        },
        {
            "name": "new_api",
            "call_template_type": "http",
            "url": "https://api.example.com/utcp"
        }
    ]
})
```

**Phase 3: Full UTCP**
```python
# Pure UTCP implementation
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "native_utcp",
        "call_template_type": "http",
        "url": "https://api.example.com/utcp"
    }]
})
```

## Debugging and Troubleshooting

### Enable Debug Logging
```python
import logging
logging.getLogger('utcp.mcp').setLevel(logging.DEBUG)

try:
    client = await UtcpClient.create(config=mcp_config)
    tools = await client.list_tools()
except TimeoutError:
    print("MCP server connection timed out")
```

### List Available Tools
```python
# Discover tools from MCP server
tools = await client.list_tools()
print(f"Available tools: {[tool.name for tool in tools]}")
```

### Connection Testing
```python
@pytest.mark.asyncio
async def test_mcp_integration():
    client = await UtcpClient.create(config={
        "manual_call_templates": [{
            "name": "test_mcp",
            "call_template_type": "mcp",
            "config": {
                "mcpServers": {
                    "test": {
                        "command": "python",
                        "args": ["-m", "test_mcp_server"]
                    }
                }
            }
        }]
    })
    
    tools = await client.list_tools()
    assert len(tools) > 0
    
    result = await client.call_tool("test_mcp.echo", {"message": "test"})
    assert result["message"] == "test"
```

## Error Handling

```python
from utcp.exceptions import ToolCallError

try:
    result = await client.call_tool("mcp_server.tool", {"arg": "value"})
except ToolCallError as e:
    print(f"MCP tool call failed: {e}")
    # Check if it's a connection issue, authentication error, etc.
```

## Performance Considerations

- **Session Reuse**: MCP plugin reuses connections when possible
- **Timeout Configuration**: Set appropriate timeouts for MCP operations
- **Resource Cleanup**: Sessions are automatically cleaned up
- **Concurrent Calls**: Multiple tools can be called concurrently

## Related Documentation

- [Main UTCP Documentation](../../../README.md)
- [Core Package Documentation](../../../core/README.md)
- [HTTP Plugin](../http/README.md)
- [CLI Plugin](../cli/README.md)
- [Text Plugin](../text/README.md)
- [MCP Specification](https://modelcontextprotocol.io/)

## Examples

For complete examples, see the [UTCP examples repository](https://github.com/universal-tool-calling-protocol/utcp-examples).
