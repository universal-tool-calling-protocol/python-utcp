"""UTCP manual data structure for tool discovery.

This module defines the UtcpManual model that standardizes the format for
tool provider responses during tool discovery. It serves as the contract
between tool providers and clients for sharing available tools and their
configurations.
"""

from typing import List, Union
from pydantic import BaseModel, field_serializer, field_validator
from utcp.python_specific_tooling.tool_decorator import ToolContext
from utcp.python_specific_tooling.version import __version__
from utcp.data.tool import Tool
from utcp.data.tool import ToolSerializer
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError

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
        @utcp_tool
        def tool1():
            pass
        
        @utcp_tool
        def tool2():
            pass
        
        # Create a manual from registered tools
        manual = UtcpManual.create_from_decorators()
        
        # Manual with specific tools
        manual = UtcpManual.create_from_decorators(
            manual_version="1.0.0",
            exclude=["tool1"]
        )
        ```
    """
    utcp_version: str = __version__
    manual_version: str = "1.0.0"
    tools: List[Tool]

    @staticmethod
    def create_from_decorators(manual_version: str = "1.0.0", exclude: List[str] = []) -> "UtcpManual":
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
            manual = UtcpManual.create_from_decorators()
            
            # Create manual with specific version
            manual = UtcpManual.create_from_decorators(manual_version="1.2.0")
            ```
        """
        return UtcpManual(
            manual_version=manual_version,
            tools=[tool for tool in ToolContext.get_tools() if tool.name not in exclude]
        )

    @field_serializer("tools")
    def serialize_tools(self, tools: List[Tool]) -> List[dict]:
        return [ToolSerializer().to_dict(tool) for tool in tools]

    @field_validator("tools")
    @classmethod
    def validate_tools(cls, tools: List[Union[Tool, dict]]) -> List[Tool]:
        return [v if isinstance(v, Tool) else ToolSerializer().validate_dict(v) for v in tools]

    
class UtcpManualSerializer(Serializer[UtcpManual]):
    """Custom serializer for UtcpManual model."""
    
    def to_dict(self, obj: UtcpManual) -> dict:
        return obj.model_dump()
    
    def validate_dict(self, data: dict) -> UtcpManual:
        try:
            return UtcpManual.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid UtcpManual: " + str(e))
