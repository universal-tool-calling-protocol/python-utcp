"""UTCP manual data structure for tool discovery.

This module defines the UtcpManual model that standardizes the format for
tool provider responses during tool discovery. It serves as the contract
between tool providers and clients for sharing available tools and their
configurations.
"""

from typing import List
from pydantic import BaseModel, ConfigDict
from utcp.shared.tool import Tool, ToolContext
from utcp.version import __version__
class UtcpManual(BaseModel):
    """Standard format for tool provider responses during discovery.

    Represents the complete set of tools available from a provider, along
    with version information for compatibility checking. This format is
    returned by tool providers when clients query for available tools
    (e.g., through the `/utcp` endpoint or similar discovery mechanisms).

    The manual serves as the authoritative source of truth for what tools
    a provider offers and how they should be invoked.

    Attributes:
        version: UTCP protocol version supported by the provider.
            Defaults to the current library version.
        tools: List of available tools with their complete configurations
            including input/output schemas, descriptions, and metadata.

    Example:
        ```python
        # Create a manual from registered tools
        manual = UtcpManual.create()
        
        # Manual with specific tools
        manual = UtcpManual(
            version="1.0.0",
            tools=[tool1, tool2, tool3]
        )
        ```
    """
    version: str = __version__
    tools: List[Tool]

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @staticmethod
    def create(version: str = __version__) -> "UtcpManual":
        """Create a UTCP manual from the global tool registry.

        Convenience method that creates a manual containing all tools
        currently registered in the global ToolContext. This is typically
        used by tool providers to generate their discovery response.

        Args:
            version: UTCP protocol version to include in the manual.
                Defaults to the current library version.

        Returns:
            UtcpManual containing all registered tools and the specified version.

        Example:
            ```python
            # Create manual with default version
            manual = UtcpManual.create()
            
            # Create manual with specific version
            manual = UtcpManual.create(version="1.2.0")
            ```
        """
        return UtcpManual(
            version=version,
            tools=ToolContext.get_tools()
        )
