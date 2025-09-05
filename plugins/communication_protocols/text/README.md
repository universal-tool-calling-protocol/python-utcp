# UTCP Text Plugin

[![PyPI Downloads](https://static.pepy.tech/badge/utcp-text)](https://pepy.tech/projects/utcp-text)

Text-based resource plugin for UTCP, supporting both local files and remote URLs for tool definitions and OpenAPI specifications.

## Features

- **Local File Support**: Read UTCP manuals from JSON/YAML files
- **Remote URL Support**: Fetch OpenAPI specs and tool definitions from URLs
- **OpenAPI Integration**: Automatic conversion of OpenAPI specs to UTCP tools
- **Multiple Formats**: Supports JSON, YAML, and OpenAPI specifications
- **Static Configuration**: Perfect for offline or air-gapped environments
- **Version Control**: Tool definitions can be versioned with your code
- **No Authentication**: Simple text-based resources without auth requirements

## Installation

```bash
pip install utcp-text
```

## Quick Start

### Local File
```python
from utcp.utcp_client import UtcpClient

# Load tools from local file
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "local_tools",
        "call_template_type": "text",
        "file_path": "./tools/my_manual.json"
    }]
})
```

### Remote OpenAPI Spec
```python
# Load tools from remote OpenAPI specification
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "petstore_api",
        "call_template_type": "text",
        "file_path": "https://petstore3.swagger.io/api/v3/openapi.json"
    }]
})

result = await client.call_tool("petstore_api.getPetById", {"petId": "1"})
```

## Configuration Examples

### Local Files
```json
{
  "name": "file_tools",
  "call_template_type": "text",
  "file_path": "./manuals/tools.json"
}
```

### Remote OpenAPI Specifications
```json
{
  "name": "github_api",
  "call_template_type": "text",
  "file_path": "https://api.github.com/openapi.json"
}
```

```json
{
  "name": "stripe_api",
  "call_template_type": "text",
  "file_path": "https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json"
}
```

### Remote UTCP Manuals
```json
{
  "name": "shared_tools",
  "call_template_type": "text",
  "file_path": "https://example.com/shared-tools.yaml"
}
```

### Multiple Sources (Local + Remote)
```json
{
  "manual_call_templates": [
    {
      "name": "local_tools",
      "call_template_type": "text",
      "file_path": "./tools/core.json"
    },
    {
      "name": "petstore",
      "call_template_type": "text",
      "file_path": "https://petstore3.swagger.io/api/v3/openapi.json"
    },
    {
      "name": "jsonplaceholder",
      "call_template_type": "text",
      "file_path": "https://jsonplaceholder.typicode.com/openapi.json"
    }
  ]
}
```

## Remote OpenAPI Examples

### Popular Public APIs
```python
# JSONPlaceholder API
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "jsonplaceholder",
        "call_template_type": "text",
        "file_path": "https://jsonplaceholder.typicode.com/openapi.json"
    }]
})

# Get all posts
posts = await client.call_tool("jsonplaceholder.getPosts", {})

# Get specific user
user = await client.call_tool("jsonplaceholder.getUser", {"id": "1"})
```

### OpenAPI with Base URL Override
```python
# Use OpenAPI spec but override the base URL
from utcp_text.text_communication_protocol import TextCommunicationProtocol

# The text plugin will automatically detect OpenAPI format
# and convert it to UTCP tools with the original base URL
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "api_staging",
        "call_template_type": "text",
        "file_path": "https://api.example.com/openapi.json"
        # Tools will use the base URL from the OpenAPI spec
    }]
})
```

## File Format Support

### Local UTCP Manual (JSON)
```json
{
  "manual_version": "1.0.0",
  "utcp_version": "1.0.1",
  "tools": [
    {
      "name": "calculate",
      "description": "Perform mathematical calculations",
      "tool_call_template": {
        "call_template_type": "cli",
        "command_name": "bc -l"
      }
    }
  ]
}
```

### Local UTCP Manual (YAML)
```yaml
manual_version: "1.0.0"
utcp_version: "1.0.1"
tools:
  - name: "file_info"
    description: "Get file information"
    tool_call_template:
      call_template_type: "cli"
      command_name: "stat ${path}"
```

### Remote OpenAPI Specification
The text plugin automatically detects and converts OpenAPI 2.0 and 3.0 specifications:

```python
# These URLs will be automatically converted from OpenAPI to UTCP
openapi_sources = [
    "https://petstore3.swagger.io/api/v3/openapi.json",
    "https://api.github.com/openapi.json",
    "https://httpbin.org/spec.json",
    "https://jsonplaceholder.typicode.com/openapi.json"
]
```

## Use Cases

### Development with Public APIs
```python
# Quickly integrate with public APIs using their OpenAPI specs
client = await UtcpClient.create(config={
    "manual_call_templates": [
        {
            "name": "httpbin",
            "call_template_type": "text",
            "file_path": "https://httpbin.org/spec.json"
        },
        {
            "name": "petstore",
            "call_template_type": "text", 
            "file_path": "https://petstore3.swagger.io/api/v3/openapi.json"
        }
    ]
})
```

### Offline Development
```json
{
  "name": "offline_tools",
  "call_template_type": "text",
  "file_path": "./cached-apis/github-openapi.json"
}
```

### Configuration Management
```json
{
  "name": "shared_config",
  "call_template_type": "text",
  "file_path": "https://config.company.com/utcp-tools.yaml"
}
```

### API Documentation Integration
```python
# Load API definitions directly from documentation sites
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "company_api",
        "call_template_type": "text",
        "file_path": "https://docs.company.com/api/openapi.yaml"
    }]
})
```

## Error Handling

### Local Files
```python
try:
    client = await UtcpClient.create(config={
        "manual_call_templates": [{
            "name": "local_tools",
            "call_template_type": "text",
            "file_path": "./nonexistent.json"
        }]
    })
except FileNotFoundError:
    print("Local tool definition file not found")
```

### Remote URLs
```python
import aiohttp

try:
    client = await UtcpClient.create(config={
        "manual_call_templates": [{
            "name": "remote_api",
            "call_template_type": "text",
            "file_path": "https://api.example.com/openapi.json"
        }]
    })
except aiohttp.ClientError:
    print("Failed to fetch remote OpenAPI specification")
```

## Performance Considerations

### Caching Remote Resources
- Remote URLs are fetched each time the client is created
- Consider caching OpenAPI specs locally for production use
- Use local files for frequently accessed specifications

### Network Dependencies
- Remote URLs require internet connectivity
- Consider fallback to cached local copies
- Implement retry logic for network failures

## Best Practices

### Remote OpenAPI Usage
- Verify OpenAPI spec URLs are stable and versioned
- Cache frequently used specs locally
- Monitor for API specification changes
- Use specific version URLs when available

### Local File Management
- Store tool definitions in version control
- Use relative paths for portability
- Organize files by functionality or environment

### Hybrid Approach
```python
# Combine local tools with remote APIs
client = await UtcpClient.create(config={
    "manual_call_templates": [
        # Local custom tools
        {
            "name": "custom_tools",
            "call_template_type": "text",
            "file_path": "./tools/custom.json"
        },
        # Remote public API
        {
            "name": "github_api",
            "call_template_type": "text",
            "file_path": "https://api.github.com/openapi.json"
        }
    ]
})
```

## Testing

```python
import pytest
from utcp.utcp_client import UtcpClient

@pytest.mark.asyncio
async def test_remote_openapi():
    client = await UtcpClient.create(config={
        "manual_call_templates": [{
            "name": "httpbin",
            "call_template_type": "text",
            "file_path": "https://httpbin.org/spec.json"
        }]
    })
    
    tools = await client.list_tools()
    assert len(tools) > 0
    
    # Test a simple GET endpoint
    result = await client.call_tool("httpbin.get", {})
    assert result is not None
```

## Related Documentation

- [Main UTCP Documentation](../../../README.md)
- [Core Package Documentation](../../../core/README.md)
- [HTTP Plugin](../http/README.md) - For authenticated APIs
- [CLI Plugin](../cli/README.md)
- [MCP Plugin](../mcp/README.md)

## Examples

For complete examples, see the [UTCP examples repository](https://github.com/universal-tool-calling-protocol/utcp-examples).
