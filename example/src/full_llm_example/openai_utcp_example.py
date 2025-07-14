"""
UTCP OpenAI Integration Example

This example demonstrates how to:
1. Initialize a UTCP client with tool providers from a config file
2. For each user request, search for relevant tools.
3. Instruct OpenAI to respond with a JSON for a tool call.
4. Parse the JSON and execute the tool call using the UTCP client.
5. Return the results to OpenAI for a final response.
"""

import asyncio
import os
import json
import sys
import re
from pathlib import Path
from typing import Dict, Any, List

import openai
from dotenv import load_dotenv

from utcp.client.utcp_client import UtcpClient
from utcp.client.utcp_client_config import UtcpClientConfig, UtcpDotEnv
from utcp.shared.tool import Tool


async def initialize_utcp_client() -> UtcpClient:
    """Initialize the UTCP client with configuration."""
    # Create a configuration for the UTCP client
    config = UtcpClientConfig(
        providers_file_path=str(Path(__file__).parent / "providers.json"),
        load_variables_from=[
            UtcpDotEnv(env_file_path=str(Path(__file__).parent / ".env"))
        ]
    )
    
    # Create and return the UTCP client
    client = await UtcpClient.create(config)
    return client

def format_tools_for_prompt(tools: List[Tool]) -> str:
    """Convert UTCP tools to a JSON string for the prompt."""
    tool_list = []
    for tool in tools:
        tool_list.append(tool.model_dump())
    return json.dumps(tool_list, indent=2)

async def get_openai_response(messages: List[Dict[str, str]]) -> str:
    """Get a response from OpenAI."""
    client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
    )
    
    return response.choices[0].message.content

async def main():
    """Main function to demonstrate OpenAI with UTCP integration."""
    load_dotenv(Path(__file__).parent / ".env")
    
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not found in environment variables")
        print("Please set it in the .env file")
        sys.exit(1)
    
    print("Initializing UTCP client...")
    utcp_client = await initialize_utcp_client()
    print("UTCP client initialized successfully.")

    conversation_history = []

    while True:
        user_prompt = input("\nEnter your prompt (or 'exit' to quit): ")
        if user_prompt.lower() in ["exit", "quit"]:
            break

        print("\nSearching for relevant tools...")
        relevant_tools = await utcp_client.search_tools(user_prompt, limit=10)
        
        if relevant_tools:
            print(f"Found {len(relevant_tools)} relevant tools.")
            for tool in relevant_tools:
                print(f"- {tool.name}")
        else:
            print("No relevant tools found.")

        tools_json_string = format_tools_for_prompt(relevant_tools)

        system_prompt = (
            "You are a helpful assistant. When you need to use a tool, you MUST respond with a JSON object "
            "with 'tool_name' and 'arguments' keys. Do not add any other text. The arguments must be a JSON object."
            "For example: {\"tool_name\": \"some_tool.name\", \"arguments\": {\"arg1\": \"value1\"}}. "
            f"Here are the available tools:\n{tools_json_string}"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_prompt})

        print("\nSending request to OpenAI...")
        assistant_response = await get_openai_response(messages)

        json_match = re.search(r'```json\n({.*?})\n```', assistant_response, re.DOTALL)
        if not json_match:
            json_match = re.search(r'({.*})', assistant_response, re.DOTALL)

        if json_match:
            json_string = json_match.group(1)
            try:
                tool_call_data = json.loads(json_string)
                if "tool_name" in tool_call_data and "arguments" in tool_call_data:
                    tool_name = tool_call_data["tool_name"]
                    arguments = tool_call_data["arguments"]
                    
                    print(f"\nExecuting tool call: {tool_name}")
                    print(f"Arguments: {json.dumps(arguments, indent=2)}")

                    try:
                        result = await utcp_client.call_tool(tool_name, arguments)
                        print(f"Result: {result}")
                        tool_output = str(result)
                    except Exception as e:
                        error_message = f"Error calling {tool_name}: {str(e)}"
                        print(f"Error: {error_message}")
                        tool_output = error_message

                    # Add user prompt and assistant's response to history
                    conversation_history.append({"role": "user", "content": user_prompt})
                    conversation_history.append({"role": "assistant", "content": assistant_response})

                    print("\nSending tool results to OpenAI for interpretation...")
                    
                    # Create a new list of messages for the follow-up, adding the tool output as a new user message
                    follow_up_messages = [
                        {"role": "system", "content": system_prompt},
                        *conversation_history,
                        # Provide the tool's output as a new user message for the model to process
                        {"role": "user", "content": f"Tool output: {tool_output}\n Please use the tool output to answer the users request."}
                    ]

                    final_response = await get_openai_response(follow_up_messages)
                    print(f"\nAssistant's interpretation: {final_response}")
                    conversation_history.append({"role": "assistant", "content": final_response})
                else:
                    print(f"\nAssistant: {assistant_response}")
                    conversation_history.append({"role": "user", "content": user_prompt})
                    conversation_history.append({"role": "assistant", "content": assistant_response})
            except json.JSONDecodeError:
                print(f"\nAssistant: {assistant_response}")
                conversation_history.append({"role": "user", "content": user_prompt})
                conversation_history.append({"role": "assistant", "content": assistant_response})
        else:
            print(f"\nAssistant: {assistant_response}")
            conversation_history.append({"role": "user", "content": user_prompt})
            conversation_history.append({"role": "assistant", "content": assistant_response})

if __name__ == "__main__":
    asyncio.run(main())
