from typing import List
from pydantic import BaseModel
from utcp.shared.tool import Tool
from utcp.version import __version__

"""
The response returned by a tool provider when queried for available tools (e.g. through the /utcp endpoint)
"""
class UtcpManual(BaseModel):
    version: str = __version__
    tools: List[Tool]
    
