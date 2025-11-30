# UTCP Text Plugin

[![PyPI Downloads](https://static.pepy.tech/badge/utcp-text)](https://pepy.tech/projects/utcp-text)

A text content plugin for UTCP. This plugin allows you to pass UTCP manuals or tool definitions directly as text content, without requiring file system access. It's browser-compatible and ideal for embedded configurations.

## Features

- **Direct Text Content**: Pass UTCP manuals or tool definitions directly as strings.
- **Browser Compatible**: No file system access required, works in browser environments.
- **JSON & YAML Support**: Parses both JSON and YAML formatted content.
- **OpenAPI Support**: Automatically converts OpenAPI specs to UTCP tools with optional authentication.
- **Base URL Override**: Override API base URLs when converting OpenAPI specs.
- **Tool Authentication**: Supports authentication for generated tools from OpenAPI specs via `auth_tools`.

## Installation

```bash
pip install utcp-text
```

## How It Works

The Text plugin operates in two main ways:

1.  **Tool Discovery (`register_manual`)**: It parses the `content` field directly as a UTCP manual or OpenAPI spec. This is how the `UtcpClient` discovers what tools can be called.
2.  **Tool Execution (`call_tool`)**: When you call a tool, the plugin returns the `content` field directly.

**Note**: For file-based tool definitions, use the `utcp-file` plugin instead.

## Quick Start

Here is a complete example demonstrating how to define and use tools with direct text content.

### 1. Define Tools with Inline Content

```python
import asyncio
import json
from utcp.utcp_client import UtcpClient

# Define a UTCP manual as a Python dict, then convert to JSON string
manual_content = json.dumps({
    "manual_version": "1.0.0",
    "utcp_version": "1.0.2",
    "tools": [
        {
            "name": "get_mock_user",
            "description": "Returns a mock user profile.",
            "tool_call_template": {
                "call_template_type": "text",
                "content": json.dumps({
                    "id": 123,
                    "name": "John Doe",
                    "email": "john.doe@example.com"
                })
            }
        }
    ]
})

async def main():
    # Create a client with direct text content
    client = await UtcpClient.create(config={
        "manual_call_templates": [{
            "name": "inline_tools",
            "call_template_type": "text",
            "content": manual_content
        }]
    })

    # List the tools to confirm it was loaded
    tools = await client.list_tools()
    print("Available tools:", [tool.name for tool in tools])

    # Call the tool
    result = await client.call_tool("inline_tools.get_mock_user", {})
    
    print("\nTool Result:")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Using with OpenAPI Specs

You can also pass OpenAPI specs directly as text content:

```python
import asyncio
import json
from utcp.utcp_client import UtcpClient

openapi_spec = json.dumps({
    "openapi": "3.0.0",
    "info": {"title": "Pet Store", "version": "1.0.0"},
    "servers": [{"url": "https://api.example.com"}],
    "paths": {
        "/pets": {
            "get": {
                "operationId": "listPets",
                "summary": "List all pets",
                "responses": {"200": {"description": "Success"}}
            }
        }
    }
})

async def main():
    client = await UtcpClient.create(config={
        "manual_call_templates": [{
            "name": "pet_api",
            "call_template_type": "text",
            "content": openapi_spec,
            "base_url": "https://api.petstore.io/v1"  # Optional: override base URL
        }]
    })

    tools = await client.list_tools()
    print("Available tools:", [tool.name for tool in tools])

if __name__ == "__main__":
    asyncio.run(main())
```

## Use Cases

- **Embedded Configurations**: Embed tool definitions directly in your application code.
- **Browser Applications**: Use UTCP in browser environments without file system access.
- **Dynamic Tool Generation**: Generate tool definitions programmatically at runtime.
- **Testing**: Define mock tools inline for unit tests.

## Related Documentation

- [Main UTCP Documentation](../../../README.md)
- [Core Package Documentation](../../../core/README.md)
- [File Plugin](../file/README.md) - For file-based tool definitions.
- [HTTP Plugin](../http/README.md) - For calling real web APIs.
- [CLI Plugin](../cli/README.md) - For executing command-line tools.
