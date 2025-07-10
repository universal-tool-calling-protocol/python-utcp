from typing import List
from pydantic import BaseModel, ConfigDict
from utcp.shared.tool import Tool, ToolContext
from utcp.version import __version__

"""
The response returned by a tool provider when queried for available tools (e.g. through the /utcp endpoint)
"""
class UtcpManual(BaseModel):
    version: str = __version__
    tools: List[Tool]

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @staticmethod
    def create(version: str = __version__) -> "UtcpManual":
        """Get the UTCP manual with version and tools."""
        return UtcpManual(
            version=version,
            tools=ToolContext.get_tools()
        )
