
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
    """Configuration container for multiple MCP servers.

    Holds a collection of named MCP server configurations, allowing
    a single MCP provider to manage multiple server connections.

    Attributes:
        mcpServers: Dictionary mapping server names to their configurations.
    """
    
    mcpServers: Dict[str, Dict[str, Any]]

class McpCallTemplate(CallTemplate):
    """Provider configuration for Model Context Protocol (MCP) tools.

    Enables communication with MCP servers that provide structured tool
    interfaces. Supports both stdio (local process) and HTTP (remote)
    transport methods.

    Attributes:
        call_template_type: Always "mcp" for MCP providers.
        config: Configuration object containing MCP server definitions.
            This follows the same format as the official MCP server configuration.
        auth: Optional OAuth2 authentication for HTTP-based MCP servers.
    """

    call_template_type: Literal["mcp"] = "mcp"
    config: McpConfig
    auth: Optional[OAuth2Auth] = None

class McpCallTemplateSerializer(Serializer[McpCallTemplate]):
    def to_dict(self, obj: McpCallTemplate) -> dict:
        return obj.model_dump()
    
    def validate_dict(self, obj: dict) -> McpCallTemplate:
        try:
            return McpCallTemplate.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid McpCallTemplate: " + traceback.format_exc()) from e
