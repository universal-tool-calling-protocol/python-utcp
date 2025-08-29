from typing import Any, Dict, Optional, AsyncGenerator, TYPE_CHECKING
import json

from mcp_use import MCPClient
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
import logging

logger = logging.getLogger(__name__)

class McpCommunicationProtocol(CommunicationProtocol):
    """REQUIRED
    MCP transport implementation that connects to MCP servers via stdio or HTTP.
    
    This implementation uses MCPClient for simplified session management and reuses
    sessions for better performance and efficiency.
    """
    
    def __init__(self):
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}
        self._mcp_client: Optional[MCPClient] = None

    async def _ensure_mcp_client(self, manual_call_template: 'McpCallTemplate'):
        """Ensure MCPClient is initialized with the current configuration."""
        if self._mcp_client is None or self._mcp_client.config != manual_call_template.config.mcpServers:
            # Create a new MCPClient with the server configuration
            config = {"mcpServers": manual_call_template.config.mcpServers}
            self._mcp_client = MCPClient.from_dict(config)

    async def _get_or_create_session(self, server_name: str, manual_call_template: 'McpCallTemplate'):
        """Get an existing session or create a new one using MCPClient."""
        await self._ensure_mcp_client(manual_call_template)
        
        try:
            # Try to get existing session
            session = self._mcp_client.get_session(server_name)
            logger.info(f"Reusing existing session for server: {server_name}")
            return session
        except ValueError:
            # Session doesn't exist, create a new one
            logger.info(f"Creating new session for server: {server_name}")
            session = await self._mcp_client.create_session(server_name, auto_initialize=True)
            return session

    async def _cleanup_session(self, server_name: str):
        """Clean up a specific session."""
        if self._mcp_client:
            await self._mcp_client.close_session(server_name)
            logger.info(f"Cleaned up session for server: {server_name}")

    async def _cleanup_all_sessions(self):
        """Clean up all active sessions."""
        if self._mcp_client:
            await self._mcp_client.close_all_sessions()
            logger.info("Cleaned up all sessions")

    async def _list_tools_with_session(self, server_name: str, manual_call_template: 'McpCallTemplate'):
        """List tools using cached session when possible."""
        try:
            session = await self._get_or_create_session(server_name, manual_call_template)
            tools_response = await session.list_tools()
            # Handle both direct list return and object with .tools attribute
            if hasattr(tools_response, 'tools'):
                return tools_response.tools
            else:
                return tools_response
        except Exception as e:
            # Check if this is a session-level error
            error_message = str(e).lower()
            session_errors = [
                "connection", "transport", "session", "protocol", "closed", 
                "disconnected", "timeout", "network", "broken pipe", "eof"
            ]
            
            is_session_error = any(error_keyword in error_message for error_keyword in session_errors)
            
            if is_session_error:
                # Only restart session for connection/transport level issues
                await self._cleanup_session(server_name)
                logger.warning(f"Session-level error for list_tools, retrying with fresh session: {e}")
                
                # Retry with a fresh session
                session = await self._get_or_create_session(server_name, manual_call_template)
                tools_response = await session.list_tools()
                # Handle both direct list return and object with .tools attribute
                if hasattr(tools_response, 'tools'):
                    return tools_response.tools
                else:
                    return tools_response
            else:
                # Protocol-level error, re-raise without session restart
                logger.error(f"Protocol-level error for list_tools: {e}")
                raise

    async def _list_resources_with_session(self, server_name: str, manual_call_template: 'McpCallTemplate'):
        """List resources using cached session when possible."""
        try:
            session = await self._get_or_create_session(server_name, manual_call_template)
            resources_response = await session.list_resources()
            # Handle both direct list return and object with .resources attribute
            if hasattr(resources_response, 'resources'):
                return resources_response.resources
            else:
                return resources_response
        except Exception as e:
            # If there's an error, clean up the potentially bad session and try once more
            await self._cleanup_session(server_name)
            logger.warning(f"Session failed for list_resources, retrying: {e}")
            
            # Retry with a fresh session
            session = await self._get_or_create_session(server_name, manual_call_template)
            resources_response = await session.list_resources()
            # Handle both direct list return and object with .resources attribute
            if hasattr(resources_response, 'resources'):
                return resources_response.resources
            else:
                return resources_response

    async def _read_resource_with_session(self, server_name: str, manual_call_template: 'McpCallTemplate', resource_uri: str):
        """Read a resource using cached session when possible."""
        try:
            session = await self._get_or_create_session(server_name, manual_call_template)
            result = await session.read_resource(resource_uri)
            return result
        except Exception as e:
            # If there's an error, clean up the potentially bad session and try once more
            await self._cleanup_session(server_name)
            logger.warning(f"Session failed for read_resource '{resource_uri}', retrying: {e}")
            
            # Retry with a fresh session
            session = await self._get_or_create_session(server_name, manual_call_template)
            result = await session.read_resource(resource_uri)
            return result

    async def _handle_resource_call(self, resource_name: str, tool_call_template: 'McpCallTemplate') -> Any:
        """Handle a resource call by finding and reading the resource from the appropriate server."""
        if not tool_call_template.config or not tool_call_template.config.mcpServers:
            raise ValueError(f"No server configuration found for resource '{resource_name}'")
        
        # Try each server until we find one that has the resource
        for server_name, server_config in tool_call_template.config.mcpServers.items():
            try:
                logger.info(f"Attempting to find resource '{resource_name}' on server '{server_name}'")
                
                # List resources to find the one with matching name
                resources = await self._list_resources_with_session(server_name, tool_call_template)
                target_resource = None
                for resource in resources:
                    if resource.name == resource_name:
                        target_resource = resource
                        break
                
                if target_resource is None:
                    logger.info(f"Resource '{resource_name}' not found in server '{server_name}'")
                    continue  # Try next server
                
                # Read the resource
                logger.info(f"Reading resource '{resource_name}' with URI '{target_resource.uri}' from server '{server_name}'")
                result = await self._read_resource_with_session(server_name, tool_call_template, target_resource.uri)
                
                # Process the result
                return result.model_dump()
            except Exception as e:
                logger.error(f"Error reading resource '{resource_name}' on server '{server_name}': {e}")
                continue  # Try next server
        
        raise ValueError(f"Resource '{resource_name}' not found in any configured server")
    
    async def _call_tool_with_session(self, server_name: str, manual_call_template: 'McpCallTemplate', tool_name: str, inputs: Dict[str, Any]):
        """Call a tool using cached session when possible."""
        session = await self._get_or_create_session(server_name, manual_call_template)
        result = await session.call_tool(tool_name, arguments=inputs)
        return result

    async def register_manual(self, caller: 'UtcpClient', manual_call_template: CallTemplate) -> RegisterManualResult:
        """REQUIRED
        Register a manual with the communication protocol.
        """
        if not isinstance(manual_call_template, McpCallTemplate):
            raise ValueError("manual_call_template must be a McpCallTemplate")
        all_tools = []
        errors = []
        if manual_call_template.config and manual_call_template.config.mcpServers:
            for server_name, server_config in manual_call_template.config.mcpServers.items():
                try:
                    logger.info(f"Discovering tools for server '{server_name}' via {server_config}")
                    mcp_tools = await self._list_tools_with_session(server_name, manual_call_template)
                    logger.info(f"Discovered {len(mcp_tools)} tools for server '{server_name}'")
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
                    
                    # Register resources as tools if enabled
                    if manual_call_template.register_resources_as_tools:
                        logger.info(f"Discovering resources for server '{server_name}' to register as tools")
                        try:
                            mcp_resources = await self._list_resources_with_session(server_name, manual_call_template)
                            logger.info(f"Discovered {len(mcp_resources)} resources for server '{server_name}'")
                            for mcp_resource in mcp_resources:
                                # Convert mcp.Resource to utcp.data.tool.Tool
                                # Create a tool that reads the resource when called
                                resource_tool = Tool(
                                    name=f"resource_{mcp_resource.name}",
                                    description=f"Read resource: {mcp_resource.description or mcp_resource.name}. URI: {mcp_resource.uri}",
                                    input_schema={
                                        "type": "object",
                                        "properties": {},
                                        "required": []
                                    },
                                    output_schema={
                                        "type": "object",
                                        "properties": {
                                            "contents": {
                                                "type": "array",
                                                "description": "Resource contents"
                                            }
                                        }
                                    },
                                    tool_call_template=manual_call_template
                                )
                                all_tools.append(resource_tool)
                        except Exception as resource_error:
                            logger.warning(f"Failed to discover resources for server '{server_name}': {resource_error}")
                            # Don't add this to errors since resources are optional
                            
                except Exception as e:
                    logger.error(f"Failed to discover tools for server '{server_name}': {e}")
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
        """REQUIRED
        Call a tool using the model context protocol.
        """
        if not isinstance(tool_call_template, McpCallTemplate):
            raise ValueError("tool_call_template must be a McpCallTemplate")
        if not tool_call_template.config or not tool_call_template.config.mcpServers:
            raise ValueError(f"No server configuration found for tool '{tool_name}'")
        
        if "." in tool_name:
            tool_name = tool_name.split(".", 1)[1]
        
        # Check if this is a resource call (tools created from resources have "resource_" prefix)
        if tool_name.startswith("resource_"):
            resource_name = tool_name[9:]  # Remove "resource_" prefix
            return await self._handle_resource_call(resource_name, tool_call_template)
        
        # Try each server until we find one that has the tool
        for server_name, server_config in tool_call_template.config.mcpServers.items():
            try:
                logger.info(f"Attempting to call tool '{tool_name}' on server '{server_name}'")
                
                # First check if this server has the tool
                tools = await self._list_tools_with_session(server_name, tool_call_template)
                tool_names = [tool.name for tool in tools]
                
                if tool_name not in tool_names:
                    logger.info(f"Tool '{tool_name}' not found in server '{server_name}'")
                    continue  # Try next server
                
                # Call the tool
                result = await self._call_tool_with_session(server_name, tool_call_template, tool_name, tool_args)
                
                # Process the result
                return self._process_tool_result(result, tool_name)
            except Exception as e:
                logger.error(f"Error calling tool '{tool_name}' on server '{server_name}': {e}")
                raise e
        
        raise ValueError(f"Tool '{tool_name}' not found in any configured server")

    async def call_tool_streaming(self, caller: 'UtcpClient', tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any, None]:
        """REQUIRED
        Streaming calls are not supported for MCP protocol, so we just call the tool and return the result as one item."""
        yield self.call_tool(caller, tool_name, tool_args, tool_call_template)

    def _process_tool_result(self, result, tool_name: str) -> Any:
        logger.info(f"Processing tool result for '{tool_name}', type: {type(result)}")
        
        # Check for structured output first
        if hasattr(result, 'structured_output'):
            logger.info(f"Found structured_output: {result.structured_output}")
            return result.structured_output
        
        # Process content if available
        if hasattr(result, 'content'):
            content = result.content
            logger.info(f"Content type: {type(content)}")
            
            # Handle list content
            if isinstance(content, list):
                logger.info(f"Content is a list with {len(content)} items")
                
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
        """Deregister an MCP manual and clean up associated sessions."""
        if not isinstance(manual_call_template, McpCallTemplate):
            logger.info(f"Deregistering manual '{manual_call_template.name}' - not an MCP template")
            return
            
        logger.info(f"Deregistering manual '{manual_call_template.name}' and cleaning up sessions")
        
        # Clean up sessions for all servers in this manual
        if manual_call_template.config and manual_call_template.config.mcpServers:
            for server_name, server_config in manual_call_template.config.mcpServers.items():
                await self._cleanup_session(server_name)
                logger.info(f"Cleaned up session for server '{server_name}'")

    async def close(self) -> None:
        """Close all active sessions and clean up resources."""
        logger.info("Closing MCP communication protocol and cleaning up all sessions")
        await self._cleanup_all_sessions()
        self._session_locks.clear()
        logger.info("MCP communication protocol closed successfully")

    async def _handle_oauth2(self, auth_details: OAuth2Auth) -> str:
        """Handles OAuth2 client credentials flow, trying both body and auth header methods."""
        client_id = auth_details.client_id
        
        # Return cached token if available
        if client_id in self._oauth_tokens:
            return self._oauth_tokens[client_id]["access_token"]

        async with aiohttp.ClientSession() as session:
            # Method 1: Send credentials in the request body
            try:
                logger.info(f"Attempting OAuth2 token fetch for '{client_id}' with credentials in body.")
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
                logger.error(f"OAuth2 with credentials in body failed: {e}. Trying Basic Auth header.")
                
            # Method 2: Send credentials as Basic Auth header
            try:
                logger.info(f"Attempting OAuth2 token fetch for '{client_id}' with Basic Auth header.")
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
                logger.error(f"OAuth2 with Basic Auth header also failed: {e}")
                raise e
