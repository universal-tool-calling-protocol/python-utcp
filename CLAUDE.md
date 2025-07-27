# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the Python implementation of the Universal Tool Calling Protocol (UTCP), a flexible and scalable standard for defining and interacting with tools across various communication protocols. UTCP emphasizes scalability, interoperability, and ease of use compared to other protocols like MCP.

## Development Commands

### Building and Installation
```bash
# Create virtual environment and install dependencies
conda create --name utcp python=3.10
conda activate utcp
pip install -r requirements.txt
python -m pip install --upgrade pip

# Build the package
python -m build

# Install locally
pip install dist/utcp-<version>.tar.gz
```

### Testing
```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=src/utcp

# Run specific test files
pytest tests/client/test_openapi_converter.py
pytest tests/client/transport_interfaces/test_http_transport.py
```

### Development Dependencies
- Install dev dependencies: `pip install -e .[dev]`
- Key dev tools: pytest, pytest-asyncio, pytest-aiohttp, pytest-cov, coverage, fastapi, uvicorn

## Architecture Overview

### Core Components

**Client Architecture (`src/utcp/client/`)**:
- `UtcpClient`: Main entry point for UTCP ecosystem interaction
- `UtcpClientConfig`: Pydantic model for client configuration
- `ClientTransportInterface`: Abstract base for transport implementations
- `ToolRepository`: Interface for storing/retrieving tools (default: `InMemToolRepository`)
- `ToolSearchStrategy`: Interface for tool search algorithms (default: `TagSearchStrategy`)

**Shared Models (`src/utcp/shared/`)**:
- `Tool`: Core tool definition with inputs/outputs schemas
- `Provider`: Defines communication protocols for tools
- `UtcpManual`: Contains discovery information for tool collections
- `Auth`: Authentication models (API key, Basic, OAuth2)

**Transport Layer (`src/utcp/client/transport_interfaces/`)**:
Each transport handles protocol-specific communication:
- `HttpClientTransport`: RESTful HTTP/HTTPS APIs
- `CliTransport`: Command Line Interface tools
- `SSEClientTransport`: Server-Sent Events
- `StreamableHttpClientTransport`: HTTP chunked transfer
- `MCPTransport`: Model Context Protocol interoperability
- `TextTransport`: Local file-based tool definitions
- `GraphQLClientTransport`: GraphQL APIs

### Key Design Patterns

**Provider Registration**: Tools are discovered via `UtcpManual` objects from providers, then registered in the client's `ToolRepository`.

**Namespaced Tool Calling**: Tools are called using format `provider_name.tool_name` to avoid naming conflicts.

**OpenAPI Auto-conversion**: HTTP providers can point to OpenAPI v3 specs for automatic tool generation.

**Extensible Authentication**: Support for API keys, Basic auth, and OAuth2 with per-provider configuration.

## Configuration

### Provider Configuration
Tools are configured via `providers.json` files that specify:
- Provider name and type
- Connection details (URL, method, etc.)
- Authentication configuration
- Tool discovery endpoints

### Client Initialization
```python
client = await UtcpClient.create(
    config={
        "providers_file_path": "./providers.json",
        "load_variables_from": [{"type": "dotenv", "env_file_path": ".env"}]
    }
)
```

## File Structure

- `src/utcp/client/`: Client implementation and transport interfaces
- `src/utcp/shared/`: Shared models and utilities
- `tests/`: Comprehensive test suite with transport-specific tests
- `example/`: Complete usage examples including LLM integration
- `scripts/`: Utility scripts for OpenAPI conversion and API fetching

## Important Implementation Notes

- All async operations use `asyncio`
- Pydantic models throughout for validation and serialization
- Transport interfaces are protocol-agnostic and swappable
- Tool search supports tag-based ranking and keyword matching
- Variable substitution in configuration supports environment variables and .env files