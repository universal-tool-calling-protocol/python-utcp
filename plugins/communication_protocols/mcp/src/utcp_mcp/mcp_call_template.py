
class McpStdioServer(BaseModel):
    """Configuration for an MCP server connected via stdio transport.

    Enables communication with Model Context Protocol servers through
    standard input/output streams, typically used for local processes.

    Attributes:
        transport: Always "stdio" for stdio-based MCP servers.
        command: The command to execute to start the MCP server.
        args: Optional command-line arguments for the MCP server.
        env: Optional environment variables for the MCP server process.
    """
    transport: Literal["stdio"] = "stdio"
    command: str
    args: Optional[List[str]] = []
    env: Optional[Dict[str, str]] = {}

class McpHttpServer(BaseModel):
    """Configuration for an MCP server connected via HTTP transport.

    Enables communication with Model Context Protocol servers through
    HTTP connections, typically used for remote MCP services.

    Attributes:
        transport: Always "http" for HTTP-based MCP servers.
        url: The HTTP endpoint URL for the MCP server.
    """
    transport: Literal["http"] = "http"
    url: str

McpServer: TypeAlias = Union[McpStdioServer, McpHttpServer]
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
    
    mcpServers: Dict[str, McpServer]

class MCPProvider(CallTemplate):
    """Provider configuration for Model Context Protocol (MCP) tools.

    Enables communication with MCP servers that provide structured tool
    interfaces. Supports both stdio (local process) and HTTP (remote)
    transport methods.

    Attributes:
        type: Always "mcp" for MCP providers.
        config: Configuration object containing MCP server definitions.
            This follows the same format as the official MCP server configuration.
        auth: Optional OAuth2 authentication for HTTP-based MCP servers.
    """

    type: Literal["mcp"] = "mcp"
    config: McpConfig
    auth: Optional[OAuth2Auth] = None