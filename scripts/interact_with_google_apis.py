import asyncio
import json
from utcp.client.utcp_client import UtcpClient

async def main():
    client: UtcpClient = await UtcpClient.create(
        config={"providers_file_path": "./google_apis.json"}
    )

    tools = await client.tool_repository.get_tools()
    tool_names = [tool.name for tool in tools]

    print("\nRegistered Google API tools:")
    for tool_name in tool_names:
        print(f" - {tool_name}")

    while True:
        print("\nEnter a tool name to see its details, a JSON tool call to execute, or 'exit' to quit.")
        user_input = input("> ")

        if user_input.lower() == 'exit':
            break

        try:
            # Try to parse as JSON for a tool call
            tool_call_data = json.loads(user_input)
            if 'name' in tool_call_data and 'args' in tool_call_data:
                tool_name = tool_call_data['name']
                args = tool_call_data['args']
                print(f"\nCalling tool '{tool_name}' with arguments: {args}")
                result = await client.call_tool(tool_name, args)
                print("\nTool call result:")
                print(result)
            else:
                print("Invalid JSON for a tool call. It must have 'name' and 'args' keys.")
        except json.JSONDecodeError:
            # If not JSON, treat it as a tool name
            tool_name = user_input
            tool = await client.tool_repository.get_tool(tool_name)
            if tool:
                print(f"\nDetails for tool '{tool_name}':")
                print(tool.model_dump_json(indent=2))
            else:
                print(f"Tool '{tool_name}' not found.")

if __name__ == "__main__":
    asyncio.run(main())
