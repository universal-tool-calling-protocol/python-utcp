import asyncio
import httpx
from utcp.client.utcp_client import UtcpClient
from utcp.shared.provider import Provider, HttpProvider
from utcp.shared.tool import Tool
from utcp.shared.utcp_manual import UtcpManual
from pydantic import BaseModel
from typing import List

FASTAPI_URL = "http://localhost:8080/utcp"


async def main():
    client = UtcpClient()

    provider = HttpProvider(
        name="test_provider",
        provider_type="http",
        http_method="GET",
        url=FASTAPI_URL)

    await client.register_tool_provider(provider)

    # List all available tools
    print("Registered tools:")
    for tool in await client.tool_repository.get_tools():
        print(f" - {tool.name}")

    # Call one of the tools
    tool_to_call = (await client.tool_repository.get_tools())[0].name
    args = {"body": {"value": "test"}}

    result = await client.call_tool(tool_to_call, args)
    print(f"\nTool call result for '{tool_to_call}':")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
