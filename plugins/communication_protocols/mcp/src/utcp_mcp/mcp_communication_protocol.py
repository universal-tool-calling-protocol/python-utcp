from typing import Any, Dict, Optional, AsyncGenerator, TYPE_CHECKING
import logging
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from utcp.data.utcp_manual import UtcpManual
from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool
from utcp.data.auth_implementations import OAuth2Auth
from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.register_manual_response import RegisterManualResult
import aiohttp
from aiohttp import BasicAuth as AiohttpBasicAuth
from utcp_mcp.mcp_call_template import McpCallTemplate

if TYPE_CHECKING:
    from utcp.utcp_client import UtcpClient


class McpCommunicationProtocol(CommunicationProtocol):
    """MCP transport implementation that connects to MCP servers via stdio or HTTP.
    
    This implementation uses a session-per-operation approach where each operation
    (register, call_tool) opens a fresh session, performs the operation, and closes.
    """
    
    def __init__(self):
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}

    async def _list_tools_with_session(self, server_config: Dict[str, Any], auth: Optional[OAuth2Auth] = None):
        # Create client streams based on transport type
        if "command" in server_config and "args" in server_config:
            params = StdioServerParameters(**server_config)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_response = await session.list_tools()
                    return tools_response.tools
        elif "url" in server_config:
            # Get authentication token if OAuth2 is configured
            auth_header = None
            if auth and isinstance(auth, OAuth2Auth):
                token = await self._handle_oauth2(auth)
                auth_header = {"Authorization": f"Bearer {token}"}
            
            async with streamablehttp_client(server_config["url"], auth=auth_header) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_response = await session.list_tools()
                    return tools_response.tools
        else:
            raise ValueError(f"Unsupported MCP transport: {json.dumps(server_config)}")
    
    async def _call_tool_with_session(self, server_config: Dict[str, Any], tool_name: str, inputs: Dict[str, Any], auth: Optional[OAuth2Auth] = None):
        if "command" in server_config and "args" in server_config:
            params = StdioServerParameters(**server_config)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=inputs)
                    return result
        elif "url" in server_config:
            # Get authentication token if OAuth2 is configured
            auth_header = None
            if auth and isinstance(auth, OAuth2Auth):
                token = await self._handle_oauth2(auth)
                auth_header = {"Authorization": f"Bearer {token}"}
            
            async with streamablehttp_client(
                url=server_config["url"],
                headers=server_config.get("headers", None),
                timeout=server_config.get("timeout", 30),
                sse_read_timeout=server_config.get("sse_read_timeout", 60 * 5),
                terminate_on_close=server_config.get("terminate_on_close", True),
                auth=auth_header
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=inputs)
                    return result
        else:
            raise ValueError(f"Unsupported MCP transport: {json.dumps(server_config)}")

    async def register_manual(self, caller: 'UtcpClient', manual_call_template: CallTemplate) -> RegisterManualResult:
        if not isinstance(manual_call_template, McpCallTemplate):
            raise ValueError("manual_call_template must be a McpCallTemplate")
        all_tools = []
        errors = []
        if manual_call_template.config and manual_call_template.config.mcpServers:
            for server_name, server_config in manual_call_template.config.mcpServers.items():
                try:
                    logging.info(f"Discovering tools for server '{server_name}' via {server_config}")
                    mcp_tools = await self._list_tools_with_session(server_config, auth=manual_call_template.auth)
                    logging.info(f"Discovered {len(mcp_tools)} tools for server '{server_name}'")
                    for mcp_tool in mcp_tools:
                        # Convert mcp.Tool to utcp.data.tool.Tool
                        utcp_tool = Tool(
                            name=mcp_tool.name,
                            description=mcp_tool.description,
                            input_schema=mcp_tool.inputSchema,
                            output_schema=mcp_tool.outputSchema,
                            tool_call_template=manual_call_template
                        )
                        all_tools.append(utcp_tool)
                except Exception as e:
                    logging.error(f"Failed to discover tools for server '{server_name}': {e}")
                    errors.append(f"Failed to discover tools for server '{server_name}': {e}")
        return RegisterManualResult(
            manual_call_template=manual_call_template,
            manual=UtcpManual(
                tools=all_tools
            ),
            success=len(errors) == 0,
            errors=errors
        )

    async def call_tool(self, caller: 'UtcpClient', tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        if not isinstance(tool_call_template, McpCallTemplate):
            raise ValueError("tool_call_template must be a McpCallTemplate")
        if not tool_call_template.config or not tool_call_template.config.mcpServers:
            raise ValueError(f"No server configuration found for tool '{tool_name}'")
        
        # Try each server until we find one that has the tool
        for server_name, server_config in tool_call_template.config.mcpServers.items():
            try:
                logging.info(f"Attempting to call tool '{tool_name}' on server '{server_name}'")
                
                # First check if this server has the tool
                tools = await self._list_tools_with_session(server_config, auth=tool_call_template.auth)
                tool_names = [tool.name for tool in tools]
                
                if tool_name not in tool_names:
                    logging.info(f"Tool '{tool_name}' not found in server '{server_name}'")
                    continue  # Try next server
                
                # Call the tool
                result = await self._call_tool_with_session(server_config, tool_name, tool_args, auth=tool_call_template.auth)
                
                # Process the result
                return self._process_tool_result(result, tool_name)
            except Exception as e:
                logging.error(f"Error calling tool '{tool_name}' on server '{server_name}': {e}")
                continue  # Try next server
        
        raise ValueError(f"Tool '{tool_name}' not found in any configured server")

    async def call_tool_streaming(self, caller: 'UtcpClient', tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any, None]:
        yield self.call_tool(caller, tool_name, tool_args, tool_call_template)

    def _process_tool_result(self, result, tool_name: str) -> Any:
        logging.info(f"Processing tool result for '{tool_name}', type: {type(result)}")
        
        # Check for structured output first
        if hasattr(result, 'structured_output'):
            logging.info(f"Found structured_output: {result.structured_output}")
            return result.structured_output
        
        # Process content if available
        if hasattr(result, 'content'):
            content = result.content
            logging.info(f"Content type: {type(content)}")
            
            # Handle list content
            if isinstance(content, list):
                logging.info(f"Content is a list with {len(content)} items")
                
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

    async def deregister_manual(self, caller: 'UtcpClient', manual_call_template: CallTemplate) -> None:
        """Deregister an MCP manual. This is a no-op in session-per-operation mode."""
        logging.info(f"Deregistering manual '{manual_call_template.name}' (no-op in session-per-operation mode)")
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
                logging.info(f"Attempting OAuth2 token fetch for '{client_id}' with credentials in body.")
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
                logging.error(f"OAuth2 with credentials in body failed: {e}. Trying Basic Auth header.")
                
            # Method 2: Send credentials as Basic Auth header
            try:
                logging.info(f"Attempting OAuth2 token fetch for '{client_id}' with Basic Auth header.")
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
                logging.error(f"OAuth2 with Basic Auth header also failed: {e}")
                raise e
