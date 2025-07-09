from abc import ABC, abstractmethod
from typing import Dict, Any, List
from utcp.shared.provider import Provider
from utcp.shared.tool import Tool

class ClientTransportInterface(ABC):
    @abstractmethod
    async def register_tool_provider(self, manual_provider: Provider) -> List[Tool]:
        pass

    @abstractmethod
    async def deregister_tool_provider(self, manual_provider: Provider) -> None:
        pass

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], tool_provider: Provider) -> Any:
        pass
