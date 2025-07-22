import asyncio
import os
from pathlib import Path
import json
import re

from dotenv import load_dotenv
from agents import Agent, Runner, FunctionTool

from utcp.client.utcp_client import UtcpClient
from utcp.client.utcp_client_config import UtcpClientConfig
from utcp.shared.tool import Tool

async def initialize_utcp_client() -> UtcpClient:
    """Initialize the UTCP client with configuration."""
    config = UtcpClientConfig(
        providers_file_path=str(Path(__file__).parent / "providers.json")
    )
    return await UtcpClient.create(config)

def sanitize_tool_name(name: str) -> str:
    """
    Sanitize tool name to match OpenAI's pattern requirement: ^[a-zA-Z0-9_-]+$
    """
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    if not sanitized or not re.match(r'^[a-zA-Z0-9]', sanitized):
        sanitized = 'tool_' + sanitized
    return sanitized

def utcp_tool_to_agent_tool(utcp_client: UtcpClient, tool: Tool) -> FunctionTool:
    """
    Creates a FunctionTool that wraps a UTCP tool,
    making it compatible with the openai-agents library.
    """
    
    async def tool_invoke_handler(ctx, args: str) -> str:
        """
        Handler function for the UTCP tool invocation.
        """
        print(f"\n🤖 Agent is calling tool: {tool.name} with args: {args}")
        try:
            kwargs = json.loads(args) if args.strip() else {}
            
            result = await utcp_client.call_tool(tool.name, kwargs)
            print(f"✅ Tool {tool.name} executed successfully. Result: {result}")
            
            if isinstance(result, (dict, list)):
                return json.dumps(result)
            else:
                return str(result)
        except Exception as e:
            print(f"❌ Error calling tool {tool.name}: {e}")
            return f"Error: {str(e)}"

    params_schema = {"type": "object", "properties": {}, "required": []}
    
    if tool.inputs and tool.inputs.properties:
        for prop_name, prop_schema in tool.inputs.properties.items():
            params_schema["properties"][prop_name] = prop_schema
        
        if tool.inputs.required:
            params_schema["required"] = tool.inputs.required

    sanitized_name = sanitize_tool_name(tool.name)
    return FunctionTool(
        name=sanitized_name,
        description=tool.description or f"No description available for {tool.name}.",
        params_json_schema=params_schema,
        on_invoke_tool=tool_invoke_handler,
    )

async def main():
    """Main function to set up and run the OpenAI agent."""
    load_dotenv(Path(__file__).parent / ".env")
    
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: OPENAI_API_KEY not found. Please set it in your .env file.")
        return

    print("🚀 Initializing UTCP client...")
    try:
        utcp_client = await initialize_utcp_client()
        utcp_tools = await utcp_client.tool_repository.get_tools()
        print(f"✅ UTCP client initialized. Found {len(utcp_tools)} tools.")
    except Exception as e:
        print(f"❌ Failed to initialize UTCP client or fetch tools: {e}")
        print("   Is the server running? Try: uvicorn server:app --port 8080")
        return

    agent_tools = [utcp_tool_to_agent_tool(utcp_client, tool) for tool in utcp_tools]

    gymbro_agent = Agent(
        name="GymBro Assistant",
        instructions="You are a helpful and motivating fitness assistant named GymBro. You can get workout plans and log exercises for the user.",
        model="gpt-4o-mini",
        tools=agent_tools,
    )

    print("\n--- GymBro Assistant is ready! ---")
    print("Type your request or 'exit' to quit.")

    while True:
        user_input = input("> ")
        if user_input.lower() == "exit":
            print("💪 Keep pushing! Goodbye!")
            break
        
        try:
            response_stream = await Runner.run(
                gymbro_agent,
                user_input
            )
            
            print(response_stream)
            
        except Exception as e:
            print(f"\nAn error occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())