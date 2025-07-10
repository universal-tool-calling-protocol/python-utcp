import asyncio
import json
import argparse
import os
from typing import List
from urllib.parse import urlparse

from utcp.client.utcp_client import UtcpClient
from utcp.shared.provider import HttpProvider
from utcp.shared.tool import Tool
from utcp.shared.utcp_manual import UtcpManual


def url_to_provider_name(url: str) -> str:
    """Create a sanitized provider name from a URL."""
    parsed_url = urlparse(url)
    # Combine host and path, remove leading slash from path
    name = parsed_url.netloc + parsed_url.path
    # Replace characters that are invalid for identifiers
    return name.replace('.', '_').replace('/', '_').replace('-', '_')

async def main(urls: List[str], output_file: str):
    """
    Converts OpenAPI spec URLs to HttpProviders, registers them, and saves the tools to a UtcpManual file.
    """
    print("Initializing UTCP client...")
    client = await UtcpClient.create()

    existing_tools: List[Tool] = []
    if os.path.exists(output_file):
        print(f"Found existing manual file at {output_file}. Loading tools...")
        with open(output_file, 'r') as f:
            try:
                manual_data = json.load(f)
                # Re-create Tool objects from dicts to ensure correct types
                existing_tools = [Tool(**tool_dict) for tool_dict in manual_data.get("tools", [])]
                print(f"Loaded {len(existing_tools)} existing tools.")
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Warning: Could not parse existing manual file. It will be overwritten. Error: {e}")

    newly_added_tools: List[Tool] = []
    for url in urls:
        provider_name = url_to_provider_name(url)
        print(f"Processing URL: {url}\nProvider name: {provider_name}")
        
        provider = HttpProvider(
            name=provider_name,
            url=url
        )

        try:
            print(f"Registering provider '{provider_name}'...")
            registered_tools = await client.register_tool_provider(provider)
            newly_added_tools.extend(registered_tools)
            print(f"Successfully registered {len(registered_tools)} tools for {provider_name}.")
        except Exception as e:
            print(f"Error registering provider for {url}: {e}")

    if not newly_added_tools:
        print("No new tools were added. Exiting.")
        return

    # Combine and deduplicate tools
    existing_tool_names = {tool.name for tool in existing_tools}
    final_tools = existing_tools + [tool for tool in newly_added_tools if tool.name not in existing_tool_names]

    # Create a UtcpManual object and save it
    utcp_manual = UtcpManual(tools=final_tools)

    print(f"Saving {len(final_tools)} tools to {output_file}...")
    with open(output_file, 'w') as f:
        # Pydantic's model_dump_json handles serialization correctly
        f.write(utcp_manual.model_dump_json(indent=2))

    print("Script finished successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert OpenAPI specs to a UTCP Manual.")
    parser.add_argument("urls", nargs='+', help="One or more URLs to OpenAPI specification files.")
    parser.add_argument("-o", "--output", default="utcp_manual.json", help="Path to the output UTCP Manual JSON file.")
    
    args = parser.parse_args()
    
    asyncio.run(main(args.urls, args.output))
