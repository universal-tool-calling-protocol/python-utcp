# Universal Tool Calling Protocol (UTCP)

[![Follow Org](https://img.shields.io/github/followers/universal-tool-calling-protocol?label=Follow%20Org&logo=github)](https://github.com/universal-tool-calling-protocol)
[![PyPI Downloads](https://static.pepy.tech/badge/utcp)](https://pepy.tech/projects/utcp)
[![License](https://img.shields.io/github/license/universal-tool-calling-protocol/python-utcp)](https://github.com/universal-tool-calling-protocol/python-utcp/blob/main/LICENSE)
[![CDTM S23](https://img.shields.io/badge/CDTM-S23-0b84f3)](https://cdtm.com/)

## Introduction

The Universal Tool Calling Protocol (UTCP) is a secure, scalable standard for defining and interacting with tools across a wide variety of communication protocols. UTCP 1.0.0 introduces a modular core with a plugin-based architecture, making it more extensible, testable, and easier to package.

In contrast to other protocols, UTCP places a strong emphasis on:

*   **Scalability**: UTCP is designed to handle a large number of tools and providers without compromising performance.
*   **Extensibility**: A pluggable architecture allows developers to easily add new communication protocols, tool storage mechanisms, and search strategies without modifying the core library.
*   **Interoperability**: With a growing ecosystem of protocol plugins (including HTTP, SSE, CLI, and more), UTCP can integrate with almost any existing service or infrastructure.
*   **Ease of Use**: The protocol is built on simple, well-defined Pydantic models, making it easy for developers to implement and use.


![MCP vs. UTCP](https://github.com/user-attachments/assets/3cadfc19-8eea-4467-b606-66e580b89444)

## Repository Structure

This repository contains the complete UTCP Python implementation:

- **[`core/`](core/)** - Core `utcp` package with foundational components ([README](core/README.md))
- **[`plugins/communication_protocols/`](plugins/communication_protocols/)** - Protocol-specific plugins:
  - [`http/`](plugins/communication_protocols/http/) - HTTP/REST, SSE, streaming, OpenAPI ([README](plugins/communication_protocols/http/README.md))
  - [`cli/`](plugins/communication_protocols/cli/) - Command-line tools ([README](plugins/communication_protocols/cli/README.md))
  - [`mcp/`](plugins/communication_protocols/mcp/) - Model Context Protocol ([README](plugins/communication_protocols/mcp/README.md))
  - [`text/`](plugins/communication_protocols/text/) - File-based tools ([README](plugins/communication_protocols/text/README.md))
  - [`socket/`](plugins/communication_protocols/socket/) - TCP/UDP (🚧 In Progress)
  - [`gql/`](plugins/communication_protocols/gql/) - GraphQL (🚧 In Progress)

## Architecture Overview

UTCP uses a modular architecture with a core library and protocol plugins:

### Core Package (`utcp`)

The [`core/`](core/) directory contains the foundational components:
- **Data Models**: Pydantic models for `Tool`, `CallTemplate`, `UtcpManual`, and `Auth`
- **Client Interface**: Main `UtcpClient` for tool interaction
- **Plugin System**: Extensible interfaces for protocols, repositories, and search
- **Default Implementations**: Built-in tool storage and search strategies

## Quick Start

### Installation

Install the core library and any required protocol plugins:

```bash
# Install core + HTTP plugin (most common)
pip install utcp utcp-http

# Install additional plugins as needed
pip install utcp-cli utcp-mcp utcp-text
```

### Basic Usage

```python
from utcp.utcp_client import UtcpClient

# Create client with HTTP API
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "my_api",
        "call_template_type": "http",
        "url": "https://api.example.com/utcp"
    }]
})

# Call a tool
result = await client.call_tool("my_api.get_data", {"id": "123"})
```

## Protocol Plugins

UTCP supports multiple communication protocols through dedicated plugins:

| Plugin | Description | Status | Documentation |
|--------|-------------|--------|---------------|
| [`utcp-http`](plugins/communication_protocols/http/) | HTTP/REST APIs, SSE, streaming | ✅ Stable | [HTTP Plugin README](plugins/communication_protocols/http/README.md) |
| [`utcp-cli`](plugins/communication_protocols/cli/) | Command-line tools | ✅ Stable | [CLI Plugin README](plugins/communication_protocols/cli/README.md) |
| [`utcp-mcp`](plugins/communication_protocols/mcp/) | Model Context Protocol | ✅ Stable | [MCP Plugin README](plugins/communication_protocols/mcp/README.md) |
| [`utcp-text`](plugins/communication_protocols/text/) | Local file-based tools | ✅ Stable | [Text Plugin README](plugins/communication_protocols/text/README.md) |
| [`utcp-socket`](plugins/communication_protocols/socket/) | TCP/UDP protocols | 🚧 In Progress | [Socket Plugin README](plugins/communication_protocols/socket/README.md) |
| [`utcp-gql`](plugins/communication_protocols/gql/) | GraphQL APIs | 🚧 In Progress | [GraphQL Plugin README](plugins/communication_protocols/gql/README.md) |

For development, you can install the packages in editable mode from the cloned repository:

```bash
# Clone the repository
git clone https://github.com/universal-tool-calling-protocol/python-utcp.git
cd python-utcp

# Install the core package in editable mode with dev dependencies
pip install -e "core[dev]"

# Install a specific protocol plugin in editable mode
pip install -e plugins/communication_protocols/http
```

## Migration Guide from 0.x to 1.0.0

Version 1.0.0 introduces several breaking changes. Follow these steps to migrate your project.

1.  **Update Dependencies**: Install the new `utcp` core package and the specific protocol plugins you use (e.g., `utcp-http`, `utcp-cli`).
2.  **Configuration**:
    *   **Configuration Object**: `UtcpClient` is initialized with a `UtcpClientConfig` object, dict or a path to a JSON file containing the configuration.
    *   **Manual Call Templates**: The `providers_file_path` option is removed. Instead of a file path, you now provide a list of `manual_call_templates` directly within the `UtcpClientConfig`.
    *   **Terminology**: The term `provider` has been replaced with `call_template`, and `provider_type` is now `call_template_type`.
    *   **Streamable HTTP**: The `call_template_type` `http_stream` has been renamed to `streamable_http`.
3.  **Update Imports**: Change your imports to reflect the new modular structure. For example, `from utcp.client.transport_interfaces.http_transport import HttpProvider` becomes `from utcp_http.http_call_template import HttpCallTemplate`.
4.  **Tool Search**: If you were using the default search, the new strategy is `TagAndDescriptionWordMatchStrategy`. This is the new default and requires no changes unless you were implementing a custom strategy.
5.  **Tool Naming**: Tool names are now namespaced as `manual_name.tool_name`. The client handles this automatically.
6.  **Variable Substitution Namespacing**: Variables that are substituted in different `call_templates`, are first namespaced with the name of the manual with the `_` duplicated. So a key in a tool call template called `API_KEY` from the manual `manual_1` would be converted to `manual__1_API_KEY`.

## Usage Examples

### 1. Using the UTCP Client

**`config.json`** (Optional)

You can define a comprehensive client configuration in a JSON file. All of these fields are optional.

```json
{
  "variables": {
    "openlibrary_URL": "https://openlibrary.org/static/openapi.json"
  },
  "load_variables_from": [
    {
      "variable_loader_type": "dotenv",
      "env_file_path": ".env"
    }
  ],
  "tool_repository": {
    "tool_repository_type": "in_memory"
  },
  "tool_search_strategy": {
    "tool_search_strategy_type": "tag_and_description_word_match"
  },
  "manual_call_templates": [
    {
        "name": "openlibrary",
        "call_template_type": "http",
        "http_method": "GET",
        "url": "${URL}",
        "content_type": "application/json"
    },
  ],
  "post_processing": [
    {
        "tool_post_processor_type": "filter_dict",
        "only_include_keys": ["name", "key"],
        "only_include_tools": ["openlibrary.read_search_authors_json_search_authors_json_get"]
    }
  ]
}
```

**`client.py`**

```python
import asyncio
from utcp.utcp_client import UtcpClient
from utcp.data.utcp_client_config import UtcpClientConfig

async def main():
    # The UtcpClient can be created with a config file path, a dict, or a UtcpClientConfig object.

    # Option 1: Initialize from a config file path
    # client_from_file = await UtcpClient.create(config="./config.json")

    # Option 2: Initialize from a dictionary
    client_from_dict = await UtcpClient.create(config={
        "variables": {
            "openlibrary_URL": "https://openlibrary.org/static/openapi.json"
        },
        "load_variables_from": [
            {
                "variable_loader_type": "dotenv",
                "env_file_path": ".env"
            }
        ],
        "tool_repository": {
            "tool_repository_type": "in_memory"
        },
        "tool_search_strategy": {
            "tool_search_strategy_type": "tag_and_description_word_match"
        },
        "manual_call_templates": [
            {
                "name": "openlibrary",
                "call_template_type": "http",
                "http_method": "GET",
                "url": "${URL}",
                "content_type": "application/json"
            }
        ],
        "post_processing": [
            {
                "tool_post_processor_type": "filter_dict",
                "only_include_keys": ["name", "key"],
                "only_include_tools": ["openlibrary.read_search_authors_json_search_authors_json_get"]
            }
        ]
    })

    # Option 3: Initialize with a full-featured UtcpClientConfig object
    from utcp_http.http_call_template import HttpCallTemplate
    from utcp.data.variable_loader import VariableLoaderSerializer
    from utcp.interfaces.tool_post_processor import ToolPostProcessorConfigSerializer

    config_obj = UtcpClientConfig(
        variables={"openlibrary_URL": "https://openlibrary.org/static/openapi.json"},
        load_variables_from=[
            VariableLoaderSerializer().validate_dict({
                "variable_loader_type": "dotenv", "env_file_path": ".env"
            })
        ],
        manual_call_templates=[
            HttpCallTemplate(
                name="openlibrary",
                call_template_type="http",
                http_method="GET",
                url="${URL}",
                content_type="application/json"
            )
        ],
        post_processing=[
            ToolPostProcessorConfigSerializer().validate_dict({
                "tool_post_processor_type": "filter_dict",
                "only_include_keys": ["name", "key"],
                "only_include_tools": ["openlibrary.read_search_authors_json_search_authors_json_get"]
            })
        ]
    )
    client = await UtcpClient.create(config=config_obj)

    # Call a tool. The name is namespaced: `manual_name.tool_name`
    result = await client.call_tool(
        tool_name="openlibrary.read_search_authors_json_search_authors_json_get",
        tool_args={"q": "J. K. Rowling"}
    )

    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Providing a UTCP Manual

A `UTCPManual` describes the tools you offer. The key change is replacing `tool_provider` with `tool_call_template`.

**`server.py`**

UTCP decorator version:

```python
from fastapi import FastAPI
from utcp_http.http_call_template import HttpCallTemplate
from utcp.data.utcp_manual import UtcpManual
from utcp.python_specific_tooling.tool_decorator import utcp_tool

app = FastAPI()

# The discovery endpoint returns the tool manual
@app.get("/utcp")
def utcp_discovery():
    return UtcpManual.create_from_decorators(manual_version="1.0.0")

# The actual tool endpoint
@utcp_tool(tool_call_template=HttpCallTemplate(
    name="get_weather",
    url=f"https://example.com/api/weather",
    http_method="GET"
), tags=["weather"])
@app.get("/api/weather")
def get_weather(location: str):
    return {"temperature": 22.5, "conditions": "Sunny"}
```


No UTCP dependencies server version:

```python
from fastapi import FastAPI

app = FastAPI()

# The discovery endpoint returns the tool manual
@app.get("/utcp")
def utcp_discovery():
    return {
        "manual_version": "1.0.0",
        "utcp_version": "1.0.2",
        "tools": [
            {
                "name": "get_weather",
                "description": "Get current weather for a location",
                "tags": ["weather"],
                "inputs": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"}
                    }
                },
                "outputs": {
                    "type": "object",
                    "properties": {
                        "temperature": {"type": "number"},
                        "conditions": {"type": "string"}
                    }
                },
                "tool_call_template": {
                    "call_template_type": "http",
                    "url": "https://example.com/api/weather",
                    "http_method": "GET"
                }
            }
        ]
    }

# The actual tool endpoint
@app.get("/api/weather")
def get_weather(location: str):
    return {"temperature": 22.5, "conditions": "Sunny"}
```

### 3. Full examples

You can find full examples in the [examples repository](https://github.com/universal-tool-calling-protocol/utcp-examples).

## Protocol Specification

### `UtcpManual` and `Tool` Models

The `tool_provider` object inside a `Tool` has been replaced by `tool_call_template`.

```json
{
  "manual_version": "string",
  "utcp_version": "string",
  "tools": [
    {
      "name": "string",
      "description": "string",
      "inputs": { ... },
      "outputs": { ... },
      "tags": ["string"],
      "tool_call_template": {
        "call_template_type": "http",
        "url": "https://...",
        "http_method": "GET"
      }
    }
  ]
}
```

## Call Template Configuration Examples

Configuration examples for each protocol. Remember to replace `provider_type` with `call_template_type`.

### HTTP Call Template

```json
{
  "name": "my_rest_api",
  "call_template_type": "http", // Required
  "url": "https://api.example.com/users/{user_id}", // Required
  "http_method": "POST", // Required, default: "GET"
  "content_type": "application/json", // Optional, default: "application/json"
  "auth": { // Optional, example using ApiKeyAuth for a Bearer token. The client must prepend "Bearer " to the token.
    "auth_type": "api_key",
    "api_key": "Bearer $API_KEY", // Required
    "var_name": "Authorization", // Optional, default: "X-Api-Key"
    "location": "header" // Optional, default: "header"
  },
  "headers": { // Optional
    "X-Custom-Header": "value"
  },
  "body_field": "body", // Optional, default: "body"
  "header_fields": ["user_id"] // Optional
}
```

### SSE (Server-Sent Events) Call Template

```json
{
  "name": "my_sse_stream",
  "call_template_type": "sse", // Required
  "url": "https://api.example.com/events", // Required
  "event_type": "message", // Optional
  "reconnect": true, // Optional, default: true
  "retry_timeout": 30000, // Optional, default: 30000 (ms)
  "auth": { // Optional, example using BasicAuth
    "auth_type": "basic",
    "username": "${USERNAME}", // Required
    "password": "${PASSWORD}" // Required
  },
  "headers": { // Optional
    "X-Client-ID": "12345"
  },
  "body_field": null, // Optional
  "header_fields": [] // Optional
}
```

### Streamable HTTP Call Template

Note the name change from `http_stream` to `streamable_http`.

```json
{
  "name": "streaming_data_source",
  "call_template_type": "streamable_http", // Required
  "url": "https://api.example.com/stream", // Required
  "http_method": "POST", // Optional, default: "GET"
  "content_type": "application/octet-stream", // Optional, default: "application/octet-stream"
  "chunk_size": 4096, // Optional, default: 4096
  "timeout": 60000, // Optional, default: 60000 (ms)
  "auth": null, // Optional
  "headers": {}, // Optional
  "body_field": "data", // Optional
  "header_fields": [] // Optional
}
```

### CLI Call Template

```json
{
  "name": "my_cli_tool",
  "call_template_type": "cli", // Required
  "commands": [ // Required - array of commands to execute in sequence
    {
      "command": "cd UTCP_ARG_target_dir_UTCP_END",
      "append_to_final_output": false // Optional, default is false if not last command
    },
    {
      "command": "my-command --input UTCP_ARG_input_file_UTCP_END"
      // append_to_final_output defaults to true for last command
    }
  ],
  "env_vars": { // Optional
    "MY_VAR": "my_value"
  },
  "working_dir": "/path/to/working/directory", // Optional
  "auth": null // Optional (always null for CLI)
}
```

**Notes:**
- Commands execute in a single subprocess (PowerShell on Windows, Bash on Unix)
- Use `UTCP_ARG_argname_UTCP_END` placeholders for arguments
- Reference previous command output with `$CMD_0_OUTPUT`, `$CMD_1_OUTPUT`, etc.
- Only the last command's output is returned by default

### Text Call Template

```json
{
  "name": "my_text_manual",
  "call_template_type": "text", // Required
  "file_path": "./manuals/my_manual.json", // Required
  "auth": null // Optional (always null for Text)
}
```

### MCP (Model Context Protocol) Call Template

```json
{
  "name": "my_mcp_server",
  "call_template_type": "mcp", // Required
  "config": { // Required
    "mcpServers": {
      "server_name": {
        "transport": "stdio",
        "command": ["python", "-m", "my_mcp_server"]
      }
    }
  },
  "auth": { // Optional, example using OAuth2
    "auth_type": "oauth2",
    "token_url": "https://auth.example.com/token", // Required
    "client_id": "${CLIENT_ID}", // Required
    "client_secret": "${CLIENT_SECRET}", // Required
    "scope": "read:tools" // Optional
  }
}
```

## Testing

The testing structure has been updated to reflect the new core/plugin split.

### Running Tests

To run all tests for the core library and all plugins:
```bash
# Ensure you have installed all dev dependencies
python -m pytest
```

To run tests for a specific package (e.g., the core library):
```bash
python -m pytest core/tests/
```

To run tests for a specific plugin (e.g., HTTP):
```bash
python -m pytest plugins/communication_protocols/http/tests/ -v
```

To run tests with coverage:
```bash
python -m pytest --cov=utcp --cov-report=xml
```

## Build

The build process now involves building each package (`core` and `plugins`) separately if needed, though they are published to PyPI independently.

1.  Create and activate a virtual environment.
2.  Install build dependencies: `pip install build`.
3.  Navigate to the package directory (e.g., `cd core`).
4.  Run the build: `python -m build`.
5.  The distributable files (`.whl` and `.tar.gz`) will be in the `dist/` directory.

## [Contributors](https://www.utcp.io/about)
