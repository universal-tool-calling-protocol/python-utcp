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

### Free Web Search and Page Fetching with Parallel

Use [Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp)
to search the web and fetch page excerpts without an account or API key.
Anonymous search uses Fast mode and has lower rate limits than authenticated
access. Add this server to an MCP manual's `config.mcpServers`:

```json
{
  "search": {
    "transport": "http",
    "url": "https://search.parallel.ai/mcp",
    "headers": {"User-Agent": "python-utcp/parallel-search-example"}
  }
}
```

The [runnable example](examples/parallel_search.py) creates a manual named
`parallel`, discovers its tools, and calls `parallel.search.web_search` and
`parallel.search.web_fetch` through `UtcpClient.call_tool`. It prints search
results and fetched page content, then closes the client. It is an opt-in
example and does not change existing client configuration.

From the repository root, install the core and MCP plugin in a Python 3.11+
virtual environment and run:

```bash
python -m venv .venv
# Activate .venv using your shell's activation command, then:
python -m pip install -e core -e plugins/communication_protocols/mcp
python plugins/communication_protocols/mcp/examples/parallel_search.py
# Or supply a search query and a specific page to fetch:
python plugins/communication_protocols/mcp/examples/parallel_search.py "Python asyncio documentation" --url https://docs.python.org/3/library/asyncio.html
```

The example calls the tools directly; no LLM or model credentials are needed.
For an agent, use the discovered input schemas to construct tool arguments and
reuse a stable `session_id` across search and fetch calls in the conversation.

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

### Child Process stderr

Stdio MCP servers often write banners, telemetry notices and auth chatter to stderr, multiplied by every server you federate. `utcp-mcp` therefore discards the child's stderr by default. To see it while debugging a server that fails to start, opt back in for the host process:

```bash
UTCP_MCP_CHILD_STDERR=inherit python your_app.py
```

Any other value, or leaving the variable unset, keeps stderr suppressed. When a stdio server fails to connect, the error log reminds you of this switch.

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
