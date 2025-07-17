from typing import List, Dict, Tuple, Optional
from utcp.shared.provider import Provider
from utcp.shared.tool import Tool
from utcp.client.tool_repository import ToolRepository

class InMemToolRepository(ToolRepository):
    def __init__(self):
        self.tools: List[Tool] = []
        self.tool_per_provider: Dict[str, Tuple[Provider, List[Tool]]] = {}

    async def save_provider_with_tools(self, provider: Provider, tools: List[Tool]) -> None:
        self.tools.extend(tools)
        self.tool_per_provider[provider.name] = (provider, tools)

    async def remove_provider(self, provider_name: str) -> None:
        if provider_name not in self.tool_per_provider:
            raise ValueError(f"Provider '{provider_name}' not found")
        tools_to_remove = self.tool_per_provider[provider_name][1]
        self.tools = [tool for tool in self.tools if tool not in tools_to_remove]
        self.tool_per_provider.pop(provider_name, None)

    async def remove_tool(self, tool_name: str) -> None:
        provider_name = tool_name.split(".")[0]
        if provider_name not in self.tool_per_provider:
            raise ValueError(f"Provider '{provider_name}' not found")
        new_tools = [tool for tool in self.tools if tool.name != tool_name]
        if len(new_tools) == len(self.tools):
            raise ValueError(f"Tool '{tool_name}' not found")
        self.tools = new_tools
        self.tool_per_provider[provider_name][1] = [tool for tool in self.tool_per_provider[provider_name][1] if tool.name != tool_name]

    async def get_tool(self, tool_name: str) -> Optional[Tool]:
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None

    async def get_tools(self) -> List[Tool]:
        return self.tools

    async def get_tools_by_provider(self, provider_name: str) -> Optional[List[Tool]]:
        return self.tool_per_provider.get(provider_name, (None, None))[1]

    async def get_provider(self, provider_name: str) -> Optional[Provider]:
        return self.tool_per_provider.get(provider_name, (None, None))[0]

    async def get_providers(self) -> List[Provider]:
        return [provider for provider, _ in self.tool_per_provider.values()]
