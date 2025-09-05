# Universal Tool Calling Protocol (UTCP) 1.0.1

[![PyPI Downloads](https://static.pepy.tech/badge/utcp)](https://pepy.tech/projects/utcp)

The core library for the Universal Tool Calling Protocol (UTCP), providing the foundational components and interfaces for building tool-calling applications.

## Overview

The UTCP core library contains:
- **Data Models**: Pydantic models for tools, manuals, and configurations
- **Client Interface**: Main `UtcpClient` for interacting with tools
- **Plugin System**: Extensible architecture for communication protocols
- **Default Implementations**: Built-in tool repositories and search strategies
- **Utility Components**: Variable substitution, post-processing, and more

## Installation

```bash
# Core library only (minimal installation)
pip install utcp

# Core + HTTP plugin (recommended for most users)
pip install utcp utcp-http
```

## Architecture

### Core Components

- **UtcpClient**: Main client interface for tool interaction
- **Tool**: Data model representing a callable tool
- **UtcpManual**: Collection of tools with metadata
- **CallTemplate**: Configuration for accessing tools via different protocols

### Plugin Interfaces

- **CommunicationProtocol**: Interface for protocol-specific communication
- **ConcurrentToolRepository**: Thread-safe tool storage interface
- **ToolSearchStrategy**: Interface for tool discovery algorithms
- **VariableSubstitutor**: Interface for configuration variable replacement
- **ToolPostProcessor**: Interface for result transformation

### Default Implementations

- **InMemToolRepository**: In-memory tool storage with async locks
- **TagAndDescriptionWordMatchStrategy**: Weighted search by tags and keywords
- **DefaultVariableSubstitutor**: Hierarchical variable resolution
- **FilterDictPostProcessor**: Dictionary key filtering
- **LimitStringsPostProcessor**: String length limiting

## Quick Start

```python
from utcp.utcp_client import UtcpClient

# Create client (requires protocol plugins)
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "my_tools",
        "call_template_type": "http",  # Requires utcp-http plugin
        "url": "https://api.example.com/utcp"
    }]
})

# Search and call tools
tools = await client.search_tools("weather")
result = await client.call_tool("my_tools.get_weather", {"city": "London"})
```

## Configuration

The core library supports flexible configuration through `UtcpClientConfig`:

```python
from utcp.utcp_client import UtcpClient
from utcp.data.utcp_client_config import UtcpClientConfig

config = UtcpClientConfig(
    variables={"API_KEY": "your-key"},
    manual_call_templates=[...],
    tool_repository={"tool_repository_type": "in_memory"},
    tool_search_strategy={"tool_search_strategy_type": "tag_and_description_word_match"},
    post_processing=[...]
)

client = await UtcpClient.create(config=config)
```

## Protocol Plugins

The core library requires protocol plugins for actual tool communication:

| Plugin | Purpose | Installation |
|--------|---------|--------------|
| [utcp-http](../plugins/communication_protocols/http/) | HTTP/REST APIs, SSE, streaming | `pip install utcp-http` |
| [utcp-cli](../plugins/communication_protocols/cli/) | Command-line tools | `pip install utcp-cli` |
| [utcp-mcp](../plugins/communication_protocols/mcp/) | Model Context Protocol | `pip install utcp-mcp` |
| [utcp-text](../plugins/communication_protocols/text/) | File-based tools, OpenAPI | `pip install utcp-text` |

## Development

### Installing for Development

```bash
git clone https://github.com/universal-tool-calling-protocol/python-utcp.git
cd python-utcp

# Install core in editable mode with dev dependencies
pip install -e core[dev]

# Install protocol plugins as needed
pip install -e plugins/communication_protocols/http
pip install -e plugins/communication_protocols/cli
```

### Running Tests

```bash
# Test core library only
python -m pytest core/tests/

# Test with coverage
python -m pytest core/tests/ --cov=utcp --cov-report=xml
```

### Building

```bash
cd core
python -m build
```

## API Reference

### UtcpClient

Main interface for tool interaction:

```python
class UtcpClient:
    @classmethod
    async def create(cls, config=None, root_dir=None) -> 'UtcpClient'
    
    async def register_manual(self, manual_call_template: CallTemplate) -> RegisterManualResult
    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Any
    async def search_tools(self, query: str, limit: int = 10) -> List[Tool]
    async def list_tools(self) -> List[Tool]
```

### Tool Model

```python
class Tool:
    name: str
    description: str
    inputs: JsonSchema
    outputs: JsonSchema
    tags: List[str]
    tool_call_template: CallTemplate
```

### CallTemplate

Base class for protocol-specific configurations:

```python
class CallTemplate:
    name: str
    call_template_type: str
    auth: Optional[Auth]
```

## Extension Points

### Custom Communication Protocol

```python
from utcp.interfaces.communication_protocol import CommunicationProtocol

class MyProtocol(CommunicationProtocol):
    async def register_manual(self, call_template, client):
        # Implementation
        pass
    
    async def call_tool(self, tool, call_template, tool_args, client):
        # Implementation
        pass
```

### Custom Search Strategy

```python
from utcp.interfaces.tool_search_strategy import ToolSearchStrategy

class MySearchStrategy(ToolSearchStrategy):
    async def search_tools(self, repository, query, limit=10):
        # Implementation
        pass
```

### Custom Post Processor

```python
from utcp.interfaces.tool_post_processor import ToolPostProcessor

class MyPostProcessor(ToolPostProcessor):
    def post_process(self, caller, tool, call_template, result):
        # Transform result
        return result
```

## Related Documentation

- [Main UTCP Documentation](../README.md)
- [HTTP Plugin](../plugins/communication_protocols/http/README.md)
- [CLI Plugin](../plugins/communication_protocols/cli/README.md)
- [MCP Plugin](../plugins/communication_protocols/mcp/README.md)
- [Text Plugin](../plugins/communication_protocols/text/README.md)

## Examples

For complete examples, see the [UTCP examples repository](https://github.com/universal-tool-calling-protocol/utcp-examples).
