from os import name
from typing import Dict, Any, List, Tuple
from utcp.shared.provider import Provider
from utcp.shared.tool import Tool
from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.client.transport_interfaces.http_transport import HttpClientTransport

class UtcpClient:
    transports: Dict[str, ClientTransportInterface] = {
        "http": HttpClientTransport()
    }
    tools: List[Tool] = []
    tool_per_provider: Dict[str, Tuple[Provider, List[Tool]]] = {}

    async def register_tool_provider(self, provider: Provider) -> List[Tool]:
        if provider.provider_type not in self.transports:
            raise ValueError(f"Unsupported provider type: {provider.type}")
        tools: List[Tool] = await self.transports[provider.provider_type].register_tool_provider(provider)
        for tool in tools:
            if not tool.name.startswith(provider.name + "."):
                tool.name = provider.name + "." + tool.name
        self.tools.extend(tools)
        self.tool_per_provider[provider.name] = (provider, tools)
        return tools

    async def deregister_tool_provider(self, provider_name: str) -> None:
        if provider_name not in self.tool_per_provider:
            raise ValueError(f"Unsupported provider type: {provider_name}")
        await self.transports[provider_name].deregister_tool_provider(self.tool_per_provider[provider_name][0])

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        provider, tools = self.tool_per_provider[tool_name.split(".")[0]]
        tool = next((t for t in tools if t.name == tool_name), None)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")

        return await self.transports[provider.provider_type].call_tool(tool_name, arguments, tool.provider)
