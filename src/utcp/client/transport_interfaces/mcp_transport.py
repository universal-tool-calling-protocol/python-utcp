import asyncio
import sys
from typing import Any, Dict, List, Optional, Callable
import logging
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from utcp.shared.provider import MCPProvider
from utcp.shared.tool import Tool
from utcp.shared.auth import OAuth2Auth
import aiohttp
from aiohttp import BasicAuth as AiohttpBasicAuth


class MCPTransport:
    """MCP transport implementation that connects to MCP servers via stdio or HTTP.
    
    This implementation uses a session-per-operation approach where each operation
    (register, call_tool) opens a fresh session, performs the operation, and closes.
    """
    
    def __init__(self, logger: Optional[Callable[[str, Any], None]] = None):
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}
        self._log = logger or (lambda *args, **kwargs: None)

    def _log(self, message: str, error: bool = False):
        """Log messages with appropriate level."""
        if error:
            logging.error(f"[MCPTransport Error] {message}")
        else:
            logging.info(f"[MCPTransport Info] {message}")

    async def _list_tools_with_session(self, server_config, auth=None):
        """List tools by creating a session."""
        # Create client streams based on transport type
        if server_config.transport == "stdio":
            params = StdioServerParameters(
                command=server_config.command,
                args=server_config.args,
                env=server_config.env
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_response = await session.list_tools()
                    return tools_response.tools
        elif server_config.transport == "http":
            # Get authentication token if OAuth2 is configured
            auth_header = None
            if auth and isinstance(auth, OAuth2Auth):
                token = await self._handle_oauth2(auth)
                auth_header = {"Authorization": f"Bearer {token}"}
            
            async with streamablehttp_client(server_config.url, auth=auth_header) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_response = await session.list_tools()
                    return tools_response.tools
        else:
            raise ValueError(f"Unsupported MCP transport: {server_config.transport}")
    
    async def _call_tool_with_session(self, server_config, tool_name, inputs, auth=None):
        """Call a tool by creating a session."""
        # Create client streams based on transport type
        if server_config.transport == "stdio":
            params = StdioServerParameters(
                command=server_config.command,
                args=server_config.args,
                env=server_config.env
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=inputs)
                    return result
        elif server_config.transport == "http":
            # Get authentication token if OAuth2 is configured
            auth_header = None
            if auth and isinstance(auth, OAuth2Auth):
                token = await self._handle_oauth2(auth)
                auth_header = {"Authorization": f"Bearer {token}"}
                
            async with streamablehttp_client(server_config.url, auth=auth_header) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=inputs)
                    return result
        else:
            raise ValueError(f"Unsupported MCP transport: {server_config.transport}")

    async def register_tool_provider(self, manual_provider: MCPProvider) -> List[Tool]:
        """Register an MCP provider and discover its tools."""
        all_tools = []
        if manual_provider.config and manual_provider.config.mcpServers:
            for server_name, server_config in manual_provider.config.mcpServers.items():
                try:
                    self._log(f"Discovering tools for server '{server_name}' via {server_config.transport}")
                    tools = await self._list_tools_with_session(server_config, auth=manual_provider.auth)
                    self._log(f"Discovered {len(tools)} tools for server '{server_name}'")
                    all_tools.extend(tools)
                except Exception as e:
                    self._log(f"Failed to discover tools for server '{server_name}': {e}", error=True)
        return all_tools

    async def call_tool(self, tool_name: str, inputs: Dict[str, Any], tool_provider: MCPProvider) -> Any:
        """Call a tool by creating a fresh session to the appropriate server."""
        if not tool_provider.config or not tool_provider.config.mcpServers:
            raise ValueError(f"No server configuration found for tool '{tool_name}'")
        
        # Try each server until we find one that has the tool
        for server_name, server_config in tool_provider.config.mcpServers.items():
            try:
                self._log(f"Attempting to call tool '{tool_name}' on server '{server_name}'")
                
                # First check if this server has the tool
                tools = await self._list_tools_with_session(server_config, auth=tool_provider.auth)
                tool_names = [tool.name for tool in tools]
                
                if tool_name not in tool_names:
                    self._log(f"Tool '{tool_name}' not found in server '{server_name}'")
                    continue  # Try next server
                
                # Call the tool
                result = await self._call_tool_with_session(server_config, tool_name, inputs, auth=tool_provider.auth)
                
                # Process the result
                return self._process_tool_result(result, tool_name)
            except Exception as e:
                self._log(f"Error calling tool '{tool_name}' on server '{server_name}': {e}", error=True)
                continue  # Try next server
        
        raise ValueError(f"Tool '{tool_name}' not found in any configured server")

    def _process_tool_result(self, result, tool_name: str) -> Any:
        """Process the tool result and return the appropriate format."""
        self._log(f"Processing tool result for '{tool_name}', type: {type(result)}")
        
        # Check for structured output first
        if hasattr(result, 'structured_output'):
            self._log(f"Found structured_output: {result.structured_output}")
            return result.structured_output
        
        # Process content if available
        if hasattr(result, 'content'):
            content = result.content
            self._log(f"Content type: {type(content)}")
            
            # Handle list content
            if isinstance(content, list):
                self._log(f"Content is a list with {len(content)} items")
                
                if not content:
                    return []
                
                # For single item lists, extract the item
                if len(content) == 1:
                    item = content[0]
                    if hasattr(item, 'text'):
                        return self._parse_text_content(item.text)
                    return item
                
                # For multiple items, process all
                result_list = []
                for item in content:
                    if hasattr(item, 'text'):
                        result_list.append(self._parse_text_content(item.text))
                    else:
                        result_list.append(item)
                return result_list
            
            # Handle single TextContent
            if hasattr(content, 'text'):
                return self._parse_text_content(content.text)
            
            # Handle other content types
            if hasattr(content, 'json'):
                return content.json
            
            return content
        
        # Fallback to result attribute
        if hasattr(result, 'result'):
            return result.result
        
        return result

    def _parse_text_content(self, text: str) -> Any:
        """Parse text content, attempting JSON, numbers, or returning as string."""
        if not text:
            return text
        
        # Try JSON parsing
        try:
            if (text.strip().startswith('{') and text.strip().endswith('}')) or \
               (text.strip().startswith('[') and text.strip().endswith(']')):
                return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try number parsing
        try:
            if text.isdigit() or (text.startswith('-') and text[1:].isdigit()):
                return int(text)
            return float(text)
        except ValueError:
            pass
        
        # Return as string
        return text

    async def deregister_tool_provider(self, manual_provider: MCPProvider) -> None:
        """Deregister an MCP provider. This is a no-op in session-per-operation mode."""
        self._log(f"Deregistering provider '{manual_provider.name}' (no-op in session-per-operation mode)")
        pass

    async def _handle_oauth2(self, auth_details: OAuth2Auth) -> str:
        """Handles OAuth2 client credentials flow, trying both body and auth header methods."""
        client_id = auth_details.client_id
        
        # Return cached token if available
        if client_id in self._oauth_tokens:
            return self._oauth_tokens[client_id]["access_token"]

        async with aiohttp.ClientSession() as session:
            # Method 1: Send credentials in the request body
            try:
                self._log(f"Attempting OAuth2 token fetch for '{client_id}' with credentials in body.")
                body_data = {
                    'grant_type': 'client_credentials',
                    'client_id': client_id,
                    'client_secret': auth_details.client_secret,
                    'scope': auth_details.scope
                }
                async with session.post(auth_details.token_url, data=body_data) as response:
                    response.raise_for_status()
                    token_response = await response.json()
                    self._oauth_tokens[client_id] = token_response
                    return token_response["access_token"]
            except aiohttp.ClientError as e:
                self._log(f"OAuth2 with credentials in body failed: {e}. Trying Basic Auth header.")
                
            # Method 2: Send credentials as Basic Auth header
            try:
                self._log(f"Attempting OAuth2 token fetch for '{client_id}' with Basic Auth header.")
                header_auth = AiohttpBasicAuth(client_id, auth_details.client_secret)
                header_data = {
                    'grant_type': 'client_credentials',
                    'scope': auth_details.scope
                }
                async with session.post(auth_details.token_url, data=header_data, auth=header_auth) as response:
                    response.raise_for_status()
                    token_response = await response.json()
                    self._oauth_tokens[client_id] = token_response
                    return token_response["access_token"]
            except aiohttp.ClientError as e:
                self._log(f"OAuth2 with Basic Auth header also failed: {e}", error=True)
                raise e

    async def close(self) -> None:
        """Close the transport. This is a no-op in session-per-operation mode."""
        self._log("Closing MCP transport (no-op in session-per-operation mode)")
        pass
