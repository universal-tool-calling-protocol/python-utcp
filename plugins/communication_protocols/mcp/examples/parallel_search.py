"""Search the web and fetch a page through UTCP's HTTP MCP plugin."""

import argparse
import asyncio
import json
import uuid

from utcp.utcp_client import UtcpClient


CONFIG = {
    "manual_call_templates": [{
        "name": "parallel",
        "call_template_type": "mcp",
        "config": {
            "mcpServers": {
                "search": {
                    "transport": "http",
                    "url": "https://search.parallel.ai/mcp",
                    "headers": {"User-Agent": "python-utcp/parallel-search-example"},
                }
            }
        },
    }]
}


async def main(query: str, url: str) -> None:
    client = await UtcpClient.create(config=CONFIG)
    try:
        tools = await client.config.tool_repository.get_tools()
        print("Discovered tools:", ", ".join(tool.name for tool in tools))

        # Reuse one anonymous session identifier for both calls in this run.
        session_id = str(uuid.uuid4())
        search = await client.call_tool("parallel.search.web_search", {
            "objective": query,
            "search_queries": [query],
            "session_id": session_id,
        })
        print("Search result:")
        print(json.dumps(search, indent=2, ensure_ascii=False))

        page = await client.call_tool("parallel.search.web_fetch", {
            "urls": [url],
            "session_id": session_id,
        })
        print("Fetched page:")
        print(json.dumps(page, indent=2, ensure_ascii=False))
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="UTCP Python MCP plugin")
    parser.add_argument("--url", default="https://www.utcp.io/",
                        help="Page to fetch after the search")
    args = parser.parse_args()
    asyncio.run(main(args.query, args.url))
