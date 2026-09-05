"""UTCP manual data structure for tool discovery.

This module defines the UtcpManual model that standardizes the format for
tool provider responses during tool discovery. It serves as the contract
between tool providers and clients for sharing available tools and their
configurations.
"""

import logging
from typing import List, Union, Optional, Any
from pydantic import BaseModel, ConfigDict, field_serializer, field_validator
from utcp.python_specific_tooling.tool_decorator import ToolContext
from utcp.python_specific_tooling.version import __version__
from utcp.data.tool import Tool
from utcp.data.tool import ToolSerializer
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
from utcp.plugins.plugin_loader import ensure_plugins_initialized
from utcp.exceptions import UtcpUnknownCallTemplateTypeError
import traceback

logger = logging.getLogger(__name__)

class UtcpManual(BaseModel):
    """REQUIRED
    Standard format for tool provider responses during discovery.

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
            including input/output schemas, descriptions, and metadata. Tools whose
            call template type is not registered in this client are skipped with a
            warning; the remaining tools load normally.

    Keys this client does not know are kept in `model_extra` and re-serialized
    unchanged, so `info` and `x-` extension keys survive a load/store round trip.

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
    model_config = ConfigDict(extra="allow")

    utcp_version: str = __version__
    manual_version: str = "1.0.0"
    tools: List[Tool]

    def __init__(self, **data):
        """Initializes the UtcpManual, ensuring plugins are loaded."""
        ensure_plugins_initialized()
        super().__init__(**data)

    @staticmethod
    def create_from_decorators(manual_version: str = "1.0.0", exclude: Optional[List[str]] = None) -> "UtcpManual":
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
        if exclude is None:
            exclude = []
        ensure_plugins_initialized()
        return UtcpManual(
            tools=[tool for tool in ToolContext.get_tools() if tool.name not in exclude],
            manual_version=manual_version,
        )

    @field_serializer("tools")
    def serialize_tools(self, tools: List[Tool]) -> List[dict]:
        return [ToolSerializer().to_dict(tool) for tool in tools]

    @field_validator("tools", mode="before")
    @classmethod
    def validate_tools(cls, tools: List[Union[Tool, dict]]) -> List[Tool]:
        validated: List[Tool] = []
        for v in tools:
            if isinstance(v, Tool):
                validated.append(v)
                continue
            try:
                validated.append(ToolSerializer().validate_dict(v))
            except UtcpUnknownCallTemplateTypeError as e:
                logger.warning(
                    "Skipping tool '%s' in manual: %s The rest of the manual is unaffected.",
                    v.get("name", "<unnamed>") if isinstance(v, dict) else "<unnamed>",
                    e,
                )
        return validated

    
class UtcpManualSerializer(Serializer[UtcpManual]):
    """REQUIRED
    Serializer for UtcpManual model."""
    
    def to_dict(self, obj: UtcpManual) -> dict:
        """REQUIRED
        Convert a UtcpManual object to a dictionary.

        Args:
            obj: The UtcpManual object to convert.

        Returns:
            The dictionary converted from the UtcpManual object.
        """
        return obj.model_dump()
    
    def validate_dict(self, data: dict) -> UtcpManual:
        """REQUIRED
        Validate a dictionary and convert it to a UtcpManual object.

        Args:
            data: The dictionary to validate and convert.

        Returns:
            The UtcpManual object converted from the dictionary.
        """
        try:
            return UtcpManual.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid UtcpManual: " + traceback.format_exc()) from e
