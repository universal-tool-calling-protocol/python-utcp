import asyncio
from os import getcwd
from utcp.client.utcp_client import UtcpClient
from utcp.client.utcp_client_config import UtcpClientConfig


async def main():
    client: UtcpClient = await UtcpClient.create(
        config=UtcpClientConfig(
            providers_file_path=str(getcwd() + "/providers.json"),
            load_variables_from=[]
        )
    )

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
