"""
UTCP Amazon Bedrock Integration Example

This example demonstrates how to:
1. Initialize a UTCP client with tool providers from a config file
2. For each user request, search for relevant tools
3. Instruct Amazon Bedrock to respond with a tool call
4. Parse the tool call and execute it using the UTCP client
5. Return the results to Amazon Bedrock for a final response
"""

import asyncio
import os
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple
import uuid
import traceback

import boto3
from dotenv import load_dotenv

from utcp.client.utcp_client import UtcpClient
from utcp.client.utcp_client_config import UtcpClientConfig, UtcpDotEnv
from utcp.shared.tool import Tool

# Global debug flag
DEBUG = False

# Amazon Bedrock model ID
# modelId = 'us.anthropic.claude-3-7-sonnet-20250219-v1:0'
modelId = 'anthropic.claude-3-sonnet-20240229-v1:0'

async def initialize_utcp_client() -> UtcpClient:
    """Initialize the UTCP client with configuration."""
    config = UtcpClientConfig(
        providers_file_path=str(Path(__file__).parent / "providers.json"),
        load_variables_from=[
            UtcpDotEnv(env_file_path=str(Path(__file__).parent / ".env"))
        ]
    )
    
    client = await UtcpClient.create(config)
    return client


def format_tools_for_bedrock(tools: List[Tool]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Convert UTCP tools to Bedrock tool format.
    
    Args:
        tools: List of UTCP tools
        
    Returns:
        Tuple containing:
        - List of tools formatted for Bedrock
        - Mapping between modified tool names and original names
    """
    bedrock_tools = []
    tool_name_mapping = {}
    
    for tool in tools:
        schema = tool.model_dump()
        
        # Create the input schema JSON
        input_schema_json = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # Add parameters to the input schema
        if "parameters" in schema and "properties" in schema["parameters"]:
            input_schema_json["properties"] = schema["parameters"]["properties"]
            if "required" in schema["parameters"]:
                input_schema_json["required"] = schema["parameters"]["required"]
        
        # Replace periods in tool name with underscores
        original_name = tool.name
        bedrock_tool_name = original_name.replace(".", "_")
        
        # Truncate if longer than 64 characters (Bedrock's limit)
        if len(bedrock_tool_name) > 64:
            short_uuid = str(uuid.uuid4())[:8]
            short_name = f"{bedrock_tool_name[:55]}_{short_uuid}"
            if DEBUG:
                print(f"Tool name '{bedrock_tool_name}' is too long, using '{short_name}' instead")
            bedrock_tool_name = short_name
        
        # Store the mapping between the modified name and original name
        tool_name_mapping[bedrock_tool_name] = original_name
        
        # Format the tool for Bedrock
        tool_spec = {
            "name": bedrock_tool_name,
            "description": tool.description,
            "inputSchema": {
                "json": input_schema_json
            }
        }
        
        bedrock_tools.append({"toolSpec": tool_spec})
    
    return bedrock_tools, tool_name_mapping


async def get_bedrock_response(messages: List[Dict[str, str]], tools=None, system_prompt=None) -> Dict[str, Any]:
    """
    Get a response from Amazon Bedrock using the Converse API.
    
    Args:
        messages: List of conversation messages
        tools: Optional list of tools formatted for Bedrock
        system_prompt: Optional system prompt
        
    Returns:
        Response from Bedrock Converse API
    """
    bedrock_runtime = boto3.client('bedrock-runtime')
    
    # Add tools configuration if provided
    tool_config = None
    if tools:
        tool_config = {"tools": tools}
        if DEBUG:
            print(f"Tool config: {json.dumps(tool_config, indent=2)}")
    
    # Prepare system prompt if provided
    system = None
    if system_prompt:
        system = [{"text": system_prompt}]
    
    try:
        # Build the API call parameters
        converse_params = {
            "modelId": modelId,
            "messages": messages
        }
        
        # Add optional parameters if provided
        if tool_config:
            converse_params["toolConfig"] = tool_config
        
        if system:
            converse_params["system"] = system
        
        if DEBUG:
            print("Calling Bedrock converse API...")
            
        response = bedrock_runtime.converse(**converse_params)
        
        if DEBUG:
            print("Bedrock API call successful")
            print(f"Response keys: {list(response.keys())}")
            print(f"Response structure: {json.dumps(response, indent=2)}")
        
        return response
    except Exception as e:
        print(f"Error in get_bedrock_response: {str(e)}")
        if DEBUG:
            print(f"Traceback: {traceback.format_exc()}")
        raise


def extract_text_from_content(content):
    """
    Extract text from a content block or list of content blocks.
    
    Args:
        content: Content block or list of content blocks
        
    Returns:
        Extracted text or empty string if no text found
    """
    if not content:
        return ""
        
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and "text" in item:
                return item["text"]
            elif isinstance(item, str):
                return item
        return ""
    elif isinstance(content, dict) and "text" in content:
        return content["text"]
    elif isinstance(content, str):
        return content
    
    return ""


async def process_tool_calls(utcp_client, tool_use, tool_name_mapping):
    """
    Process a tool call and execute it using the UTCP client.
    
    Args:
        utcp_client: UTCP client instance
        tool_use: Tool use information from Bedrock
        tool_name_mapping: Mapping between modified tool names and original names
        
    Returns:
        Dictionary containing tool result information
    """
    tool_use_id = tool_use["toolUseId"]
    modified_tool_name = tool_use["name"]
    
    # Map the modified tool name back to the original tool name
    original_tool_name = tool_name_mapping.get(modified_tool_name, modified_tool_name)
    
    print(f"\nTool call detected: {original_tool_name}")
    
    # Get the tool arguments
    tool_args = tool_use["input"]
    print(f"Arguments: {json.dumps(tool_args, indent=2)}")
    
    try:
        print(f"Executing tool call: {original_tool_name}")
        result = await utcp_client.call_tool(original_tool_name, tool_args)
        print(f"Tool execution successful!")
        print(f"Result: {result}")
        
        # Format the tool result as expected by Bedrock
        return {
            "toolResult": {
                "toolUseId": tool_use_id,
                "content": [{"json": result}]
            }
        }
    except Exception as e:
        error_message = f"Error calling {original_tool_name}: {str(e)}"
        print(f"Error: {error_message}")
        
        # Format the error as a tool result
        return {
            "toolResult": {
                "toolUseId": tool_use_id,
                "content": [{"json": {"error": str(e)}}]
            }
        }


async def main():
    """Main function to demonstrate Amazon Bedrock with UTCP integration."""
    load_dotenv(Path(__file__).parent / ".env")
    
    # Check for AWS credentials
    if not (os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY")):
        print("Warning: AWS credentials not found in environment variables")
        print("Make sure you have configured AWS credentials using AWS CLI or environment variables")
    
    print("Initializing UTCP client...")
    utcp_client = await initialize_utcp_client()
    print("UTCP client initialized successfully.")
    print(f"Using model {modelId}")

    conversation_history = []
    tool_name_mapping = {}

    system_prompt = (
        "You are a helpful assistant with access to external tools. When a user asks a question that requires "
        "using one of the available tools, you MUST use the appropriate tool rather than trying to answer from "
        "your knowledge. Always prefer using tools when they are relevant to the query. "
        "For example, if asked about news or books, use the corresponding tools to fetch real-time information. "
        "When using a tool, analyze thoroughly the required tool parameters and pass them as required."
    )

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

        # Get the formatted tools and the mapping between modified and original names
        bedrock_tools, name_mapping = format_tools_for_bedrock(relevant_tools)
        tool_name_mapping.update(name_mapping)

        # Prepare messages for Bedrock
        messages = conversation_history.copy()
        messages.append({"role": "user", "content": [{"text": user_prompt}]})

        print("\nSending request to Amazon Bedrock...")
        try:
            response = await get_bedrock_response(messages, bedrock_tools, system_prompt)
            
            # Process the response
            if "output" not in response or "message" not in response["output"]:
                print(f"Error: Unexpected response format. Missing 'output.message' key.")
                if DEBUG:
                    print(f"Full response: {response}")
                continue
                
            assistant_message = response["output"]["message"]
            conversation_history.append({"role": "user", "content": [{"text": user_prompt}]})
            
            # Check if the stop reason is tool_use
            if response.get("stopReason") == "tool_use":
                # Process tool use
                tool_results = []
                
                # Process each content block in the assistant's message
                for content_block in assistant_message["content"]:
                    if "text" in content_block:
                        print(f"\nAssistant: {content_block['text']}")
                    
                    if "toolUse" in content_block:
                        tool_result = await process_tool_calls(
                            utcp_client, 
                            content_block["toolUse"], 
                            tool_name_mapping
                        )
                        tool_results.append(tool_result)
                
                # Store assistant's response in conversation history
                conversation_history.append(assistant_message)
                
                # Send the tool results back to Bedrock
                print("\nSending tool results to Amazon Bedrock for interpretation...")
                
                # Prepare messages with tool results
                tool_response_messages = messages.copy()
                tool_response_messages.append(assistant_message)
                tool_response_messages.append({
                    "role": "user", 
                    "content": tool_results
                })
                
                # Get final response from Bedrock
                final_response = await get_bedrock_response(tool_response_messages, bedrock_tools, system_prompt)
                
                if "output" not in final_response or "message" not in final_response["output"]:
                    print(f"Error: Unexpected response format in final response.")
                    if DEBUG:
                        print(f"Full response: {final_response}")
                    continue
                    
                final_message = final_response["output"]["message"]
                final_text = extract_text_from_content(final_message.get("content", []))
                
                print(f"\nAssistant's interpretation: {final_text}")
                conversation_history.append({
                    "role": "assistant", 
                    "content": [{"text": final_text}]
                })
            else:
                # No tool call, just display the response
                assistant_text = extract_text_from_content(assistant_message.get("content", []))
                if assistant_text:
                    print(f"\nAssistant: {assistant_text}")
                    conversation_history.append({
                        "role": "assistant", 
                        "content": [{"text": assistant_text}]
                    })
                else:
                    print(f"\nError: Unexpected assistant message format")
                    if DEBUG:
                        print(f"Message: {assistant_message}")
                
        except Exception as e:
            print(f"Error calling Amazon Bedrock: {str(e)}")
            if DEBUG:
                print(f"Traceback: {traceback.format_exc()}")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="UTCP Amazon Bedrock Integration Example")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()
    
    # Set global debug flag
    DEBUG = args.debug
    
    asyncio.run(main())
