
from pydantic import BaseModel
from typing import Optional, Dict, Literal, Any
from utcp.data.auth_implementations import OAuth2Auth
from utcp.data.call_template import CallTemplate
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

"""Type alias for MCP server configurations.

Union type for all supported MCP server transport configurations,
including both stdio and HTTP-based servers.
"""

class McpConfig(BaseModel):
    """REQUIRED
    Implementing this class is not required!!!
    The McpCallTemplate just needs to support a MCP compliant server configuration.

    Configuration container for multiple MCP servers.

    Holds a collection of named MCP server configurations, allowing
    a single MCP provider to manage multiple server connections.

    Attributes:
        mcpServers: Dictionary mapping server names to their configurations.
    """
    
    mcpServers: Dict[str, Dict[str, Any]]

class McpCallTemplate(CallTemplate):
    """REQUIRED
    Provider configuration for Model Context Protocol (MCP) tools.

    Enables communication with MCP servers that provide structured tool
    interfaces. Supports both stdio (local process) and HTTP (remote)
    transport methods.

    Configuration Examples:
        Basic MCP server with stdio transport:
        ```json
        {
          "name": "mcp_server",
          "call_template_type": "mcp",
          "config": {
            "mcpServers": {
              "filesystem": {
                "command": "node",
                "args": ["mcp-server.js"],
                "env": {"NODE_ENV": "production"}
              }
            }
          }
        }
        ```

        MCP server with working directory:
        ```json
        {
          "name": "mcp_tools",
          "call_template_type": "mcp",
          "config": {
            "mcpServers": {
              "tools": {
                "command": "python",
                "args": ["-m", "mcp_server"],
                "cwd": "/app/mcp",
                "env": {
                  "PYTHONPATH": "/app",
                  "LOG_LEVEL": "INFO"
                }
              }
            }
          }
        }
        ```

        MCP server with OAuth2 authentication:
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

    Migration Examples:
        During migration (UTCP with MCP):
        ```python
        # UTCP Client with MCP plugin
        client = await UtcpClient.create()
        result = await client.call_tool("filesystem.read_file", {
            "path": "/data/file.txt"
        })
        ```

        After migration (Pure UTCP):
        ```python
        # UTCP Client with native protocol
        client = await UtcpClient.create()
        result = await client.call_tool("filesystem.read_file", {
            "path": "/data/file.txt"
        })
        ```

    Attributes:
        call_template_type: Always "mcp" for MCP providers.
        config: Configuration object containing MCP server definitions.
            This follows the same format as the official MCP server configuration.
        auth: Optional OAuth2 authentication for HTTP-based MCP servers.
        register_resources_as_tools: Whether to register MCP resources as callable tools.
            When True, server resources are exposed as tools that can be called.
            Default is False.
    """

    call_template_type: Literal["mcp"] = "mcp"
    config: McpConfig
    auth: Optional[OAuth2Auth] = None
    register_resources_as_tools: bool = False

class McpCallTemplateSerializer(Serializer[McpCallTemplate]):
    """REQUIRED
    Serializer for McpCallTemplate.
    """
    def to_dict(self, obj: McpCallTemplate) -> dict:
        """REQUIRED
        Convert McpCallTemplate to dictionary.
        """
        return obj.model_dump()
    
    def validate_dict(self, obj: dict) -> McpCallTemplate:
        """REQUIRED
        Validate and convert dictionary to McpCallTemplate.
        """
        try:
            return McpCallTemplate.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid McpCallTemplate: " + traceback.format_exc()) from e
