# UTCP Text Plugin

[![PyPI Downloads](https://static.pepy.tech/badge/utcp-text)](https://pepy.tech/projects/utcp-text)

A simple, file-based resource plugin for UTCP. This plugin allows you to define tools that return the content of a specified local file.

## Features

- **Local File Content**: Define tools that read and return the content of local files.
- **UTCP Manual Discovery**: Load tool definitions from local UTCP manual files in JSON or YAML format.
- **Static & Simple**: Ideal for returning mock data, configuration, or any static text content from a file.
- **Version Control**: Tool definitions and their corresponding content files can be versioned with your code.
- **No Authentication**: Designed for simple, local file access without authentication.

## Installation

```bash
pip install utcp-text
```

## How It Works

The Text plugin operates in two main ways:

1.  **Tool Discovery (`register_manual`)**: It can read a standard UTCP manual file (e.g., `my-tools.json`) to learn about available tools. This is how the `UtcpClient` discovers what tools can be called.
2.  **Tool Execution (`call_tool`)**: When you call a tool, the plugin looks at the `tool_call_template` associated with that tool. It expects a `text` template, and it will read and return the entire content of the `file_path` specified in that template.

**Important**: The `call_tool` function **does not** use the arguments you pass to it. It simply returns the full content of the file defined in the tool's template.

## Quick Start

Here is a complete example demonstrating how to define and use a tool that returns the content of a file.

### 1. Create a Content File

First, create a file with some content that you want your tool to return.

`./mock_data/user.json`:
```json
{
  "id": 123,
  "name": "John Doe",
  "email": "john.doe@example.com"
}
```

### 2. Create a UTCP Manual

Next, define a UTCP manual that describes your tool. The `tool_call_template` must be of type `text` and point to the content file you just created.

`./manuals/local_tools.json`:
```json
{
  "manual_version": "1.0.0",
  "utcp_version": "1.0.1",
  "tools": [
    {
      "name": "get_mock_user",
      "description": "Returns a mock user profile from a local file.",
      "tool_call_template": {
        "call_template_type": "text",
        "file_path": "./mock_data/user.json"
      }
    }
  ]
}
```

### 3. Use the Tool in Python

Finally, use the `UtcpClient` to load the manual and call the tool.

```python
import asyncio
from utcp.utcp_client import UtcpClient

async def main():
    # Create a client, providing the path to the manual.
    # The text plugin is used automatically for the "text" call_template_type.
    client = await UtcpClient.create(config={
        "manual_call_templates": [{
            "name": "local_file_tools",
            "call_template_type": "text",
            "file_path": "./manuals/local_tools.json"
        }]
    })

    # List the tools to confirm it was loaded
    tools = await client.list_tools()
    print("Available tools:", [tool.name for tool in tools])

    # Call the tool. The result will be the content of './mock_data/user.json'
    result = await client.call_tool("local_file_tools.get_mock_user", {})
    
    print("\nTool Result:")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

### Expected Output:

```
Available tools: ['local_file_tools.get_mock_user']

Tool Result:
{
  "id": 123,
  "name": "John Doe",
  "email": "john.doe@example.com"
}
```

## Use Cases

- **Mocking**: Return mock data for tests or local development without needing a live server.
- **Configuration**: Load static configuration files as tool outputs.
- **Templates**: Retrieve text templates (e.g., for emails or reports).

## Related Documentation

- [Main UTCP Documentation](../../../README.md)
- [Core Package Documentation](../../../core/README.md)
- [HTTP Plugin](../http/README.md) - For calling real web APIs.
- [CLI Plugin](../cli/README.md) - For executing command-line tools.
