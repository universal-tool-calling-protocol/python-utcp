import asyncio
import contextvars
import copy
import functools
import os
import sys
from ipaddress import IPv6Address, ip_address
from typing import Any, Dict, List, Optional, AsyncGenerator, TYPE_CHECKING, Tuple, TextIO
from urllib.parse import urlparse
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
)

logger = logging.getLogger(__name__)

# Identity of the UtcpClient behind the current call. This protocol object is a
# process-wide singleton, so manual names alone cannot identify an owner: two
# UtcpClient instances may register a manual of the same name with different
# configurations. Set by the public entry points and read where client
# ownership is tracked, without threading ``caller`` through every helper.
_CURRENT_OWNER: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar("utcp_mcp_owner", default=None)


def _with_owner(method):
    """Run an entry point with ``_CURRENT_OWNER`` bound to its ``caller``."""

    @functools.wraps(method)
    async def wrapper(self, caller, *args, **kwargs):
        token = _CURRENT_OWNER.set(id(caller) if caller is not None else None)
        try:
            return await method(self, caller, *args, **kwargs)
        finally:
            _CURRENT_OWNER.reset(token)

    return wrapper


# Hostnames considered safe to reach over plain HTTP/WS.
_LOOPBACK_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


def _is_secure_mcp_url(url: str) -> bool:
    """Return True if ``url`` is safe for the MCP plugin to connect to.

    HTTPS/WSS anywhere, or plain HTTP/WS only to a literal loopback address.
    Kept local rather than importing ``utcp_http._security`` because the MCP
    plugin does not depend on the HTTP plugin; the rule mirrors it (and the
    TypeScript ``ensureSecureMcpUrl``), including the wider loopback set
    (``0.0.0.0``, ``::``, IPv4-mapped IPv6 loopback) that a bare
    ``is_loopback`` check misses.
    """
    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https", "ws", "wss"}:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if scheme in {"https", "wss"}:
        return True
    if host in _LOOPBACK_HOSTNAMES:
        return True
    if host in {"0.0.0.0", "::"}:
        return True
    try:
        addr = ip_address(host)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    if isinstance(addr, IPv6Address):
        mapped = addr.ipv4_mapped
        if mapped is not None and mapped.is_loopback:
            return True
    return False


def _ensure_secure_mcp_url(url: str, *, context: Optional[str] = None) -> None:
    """Raise ``ValueError`` if ``url`` is not safe for the MCP plugin to reach."""
    if _is_secure_mcp_url(url):
        return
    where = f" during {context}" if context else ""
    raise ValueError(
        f"Security error{where}: URL must use HTTPS/WSS or be a literal loopback "
        f"address (localhost / 127.0.0.1 / ::1). Got: {url!r}. Plain HTTP to any "
        "other host is rejected to prevent MITM attacks and SSRF into internal services."
    )


def _has_authorization_header(server_config: Dict[str, Any]) -> bool:
    """Return True if a server config already carries an Authorization header."""
    headers = server_config.get("headers")
    if not isinstance(headers, dict):
        return False
    return any(isinstance(k, str) and k.lower() == "authorization" for k in headers)


# Environment variable that opts stdio MCP children back into writing to the
# host's stderr. Same name and semantics as the TypeScript SDK.
CHILD_STDERR_ENV_VAR = "UTCP_MCP_CHILD_STDERR"

_devnull: Optional[TextIO] = None


def _child_stderr_target() -> TextIO:
    """Return the stream stdio MCP children should write their stderr to.

    Defaults to ``os.devnull`` so a chatty server (banners, telemetry notices,
    auth chatter, multiplied by every federated server) does not flood the host
    terminal during discovery. Set ``UTCP_MCP_CHILD_STDERR=inherit`` to see it
    while debugging. A file object rather than ``subprocess.DEVNULL`` because
    the connector's contract is a text stream.
    """
    if os.environ.get(CHILD_STDERR_ENV_VAR) == "inherit":
        return sys.stderr
    global _devnull
    if _devnull is None or _devnull.closed:
        _devnull = open(os.devnull, "w")
    return _devnull


class _QuietStdioMCPClient(MCPClient):
    """``MCPClient`` that routes stdio children's stderr per ``UTCP_MCP_CHILD_STDERR``.

    ``MCPClient.from_dict`` offers no way to set the ``errlog`` that
    ``StdioConnector`` hands to the MCP SDK's ``stdio_client``, so every child
    would inherit the host's stderr. The connector only reads ``errlog`` when it
    connects, so it is enough to set it between construction and initialization.
    """

    async def create_session(self, server_name: str, auto_initialize: bool = True):
        session = await super().create_session(server_name, auto_initialize=False)
        if session is None:
            return None
        if hasattr(session.connector, "errlog"):
            session.connector.errlog = _child_stderr_target()
        if auto_initialize:
            try:
                await session.initialize()
            except Exception:
                # The base class only registers a session after a successful
                # initialize; undo the early registration, and disconnect so a
                # child that started but failed the MCP handshake does not linger.
                self.sessions.pop(server_name, None)
                if server_name in self.active_sessions:
                    self.active_sessions.remove(server_name)
                try:
                    await session.disconnect()
                except Exception as disconnect_error:
                    logger.warning(f"Failed to disconnect '{server_name}' after a failed initialize: {disconnect_error}")
                raise
        return session


class McpCommunicationProtocol(CommunicationProtocol):
    """REQUIRED
    MCP transport implementation that connects to MCP servers via stdio or HTTP.
    
    This implementation uses MCPClient for simplified session management and reuses
    sessions for better performance and efficiency.
    """
    
    def __init__(self):
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}
        # In-flight OAuth2 token fetches, keyed like the token cache (by
        # client_id), so concurrent first-time callers share one request instead
        # of each POSTing to the token endpoint.
        self._oauth_inflight: "Dict[str, asyncio.Task[str]]" = {}
        # In-flight session creations, keyed by (configuration, server), so
        # concurrent first calls for the same server dial once instead of each
        # spawning a session and leaking all but the last.
        self._session_creations: "Dict[Tuple[int, str], asyncio.Task]" = {}
        # One MCPClient per distinct server configuration. This protocol object is
        # registered once per process and shared by every manual, so a single
        # client would make manuals with different configurations evict each
        # other's sessions, including sessions still in use by a concurrent call.
        self._mcp_clients: Dict[str, MCPClient] = {}
        # Which configuration each owner (calling UtcpClient plus manual name)
        # currently uses, so a client nothing references any more can be closed
        # when a manual's configuration changes.
        self._manual_config_keys: Dict[str, str] = {}
        self._clients_lock = asyncio.Lock()
        # Clients whose shutdown failed. Kept apart from the live map so a retry
        # on close() is possible without ever overwriting a newer live client
        # for the same configuration.
        self._failed_clients: List[MCPClient] = []
    
    def _log_info(self, message: str):
        """Log informational messages."""
        logger.info(f"[McpCommunicationProtocol] {message}")

    def _log_warning(self, message: str):
        """Log warning messages."""
        logger.warning(f"[McpCommunicationProtocol] {message}")
        
    def _log_error(self, message: str):
        """Log error messages."""
        logger.error(f"[McpCommunicationProtocol] {message}")

    @staticmethod
    def _config_key(manual_call_template: 'McpCallTemplate') -> str:
        """Canonical key for a manual's connection.

        Includes the manual-level auth alongside the server configuration, so two
        manuals that share servers but not credentials get distinct clients and
        never reuse one another's injected token.
        """
        auth = manual_call_template.auth
        auth_repr = auth.model_dump() if auth is not None else None
        return json.dumps(
            {"servers": manual_call_template.config.mcpServers, "auth": auth_repr},
            sort_keys=True,
            default=str,
        )

    @staticmethod
    def _owner_key(manual_call_template: 'McpCallTemplate', config_key: str) -> str:
        """Identifies who holds a configuration: the calling UtcpClient plus the manual name."""
        return f"{_CURRENT_OWNER.get()}:{manual_call_template.name or config_key}"

    @staticmethod
    def _oauth_cache_key(auth: OAuth2Auth) -> str:
        """Key for the OAuth token cache and in-flight map.

        Keyed by the FULL configuration, not ``client_id`` alone: two manuals may
        share a client_id but point at different issuers, scopes or secrets, and
        must not receive each other's tokens. Matches the HTTP plugin. Carries
        the secret, so it is used only as a dict key and never logged.
        """
        return json.dumps([auth.token_url, auth.client_id, auth.client_secret, auth.scope or ""])

    async def _ensure_mcp_client(self, manual_call_template: 'McpCallTemplate') -> MCPClient:
        """Return the MCPClient for this manual's configuration, creating it once.

        Clients are keyed by configuration and never evicted by another manual's
        activity, so sessions are reused across calls and a call in flight on one
        configuration is never torn down by a call on another. Creation is
        serialised so two concurrent first calls cannot each spawn a client.
        """
        key = self._config_key(manual_call_template)
        manual_name = self._owner_key(manual_call_template, key)
        client = self._mcp_clients.get(key)
        if client is not None and self._manual_config_keys.get(manual_name) == key:
            return client
        # Build the connection config (URL validation + any manual OAuth2 token
        # fetch) BEFORE taking the lock. The token endpoint comes from the manual
        # and its fetch is network I/O, so holding ``_clients_lock`` across it
        # would let one slow token endpoint stall client creation for every
        # manual. ``from_dict`` spawns no processes, so a config built here but
        # left unused after losing the creation race below is inert.
        servers = await self._build_connection_servers(manual_call_template)
        async with self._clients_lock:
            client = self._mcp_clients.get(key)
            if client is None:
                client = _QuietStdioMCPClient.from_dict({"mcpServers": servers})
                self._mcp_clients[key] = client
            previous_key = self._manual_config_keys.get(manual_name)
            self._manual_config_keys[manual_name] = key
            if previous_key is not None and previous_key != key and previous_key not in self._manual_config_keys.values():
                # This manual's configuration changed and no other manual uses the
                # old one: release the old client's sessions and processes.
                stale = self._mcp_clients.pop(previous_key, None)
                if stale is not None:
                    try:
                        await stale.close_all_sessions()
                    except Exception as e:
                        # Keep it aside so close() can retry rather than leaking its processes.
                        self._failed_clients.append(stale)
                        self._log_warning(f"Failed to close sessions of a stale MCP client: {e}")
            return client

    async def _build_connection_servers(self, manual_call_template: 'McpCallTemplate') -> Dict[str, Any]:
        """Build the ``mcpServers`` mapping handed to the MCP client.

        Applies the security checks the HTTP-family plugins enforce and wires up
        manual-level OAuth2 (which was previously accepted on the call template
        but never used). Returns a deep copy so neither the caller's template nor
        the value the client is keyed by is mutated — in particular the fetched
        bearer token must never leak into the client key.
        """
        servers = copy.deepcopy(manual_call_template.config.mcpServers)
        token: Optional[str] = None
        if isinstance(manual_call_template.auth, OAuth2Auth):
            # Fetches (and validates the token endpoint of) the manual's OAuth2
            # credentials before any server connection is dialed.
            token = await self._handle_oauth2(manual_call_template.auth)
        for server_name, server_config in servers.items():
            if not isinstance(server_config, dict):
                continue
            # Validate any network URL before the client can connect to it.
            for url_field in ("url", "ws_url"):
                url = server_config.get(url_field)
                if isinstance(url, str):
                    _ensure_secure_mcp_url(url, context=f"MCP server '{server_name}' URL")
            # Inject the manual-level bearer token for HTTP servers that do not
            # already carry their own credentials. mcp-use turns ``auth_token``
            # into an ``Authorization: Bearer`` header on the connection.
            if token is not None and "url" in server_config:
                if (
                    not server_config.get("auth_token")
                    and not server_config.get("auth")
                    and not _has_authorization_header(server_config)
                ):
                    server_config["auth_token"] = token
        return servers

    async def _get_or_create_session(self, server_name: str, manual_call_template: 'McpCallTemplate'):
        """Get an existing session or create a new one using MCPClient."""
        client = await self._ensure_mcp_client(manual_call_template)

        try:
            # Try to get existing session
            session = client.get_session(server_name)
            self._log_info(f"Reusing existing session for server: {server_name}")
            return session
        except ValueError:
            pass

        # Coalesce concurrent creations for the same (configuration, server) so a
        # burst of first calls dials once instead of each spawning a session and
        # leaking all but the last. The check-and-set is synchronous, so exactly
        # one task is created.
        # Keyed by the CLIENT INSTANCE, not the configuration: a client can be
        # retired (deregistered or drained) while a creation on it is pending,
        # and a later client with the same configuration must not join that
        # task, which is bound to the retired client. The task holds a reference
        # to its client, so the id cannot be reused while the entry exists.
        inflight_key = (id(client), server_name)
        task = self._session_creations.get(inflight_key)
        if task is None:
            task = asyncio.ensure_future(
                self._create_session(server_name, client, manual_call_template)
            )
            self._session_creations[inflight_key] = task
            task.add_done_callback(lambda _t, k=inflight_key: self._session_creations.pop(k, None))
        # Shield so a cancelled waiter does not cancel the shared creation for
        # the others (see _handle_oauth2 for the same reasoning).
        return await asyncio.shield(task)

    async def _create_session(self, server_name: str, client: MCPClient, manual_call_template: 'McpCallTemplate'):
        """Create (and initialize) a new session for ``server_name`` on ``client``."""
        self._log_info(f"Creating new session for server: {server_name}")
        try:
            return await client.create_session(server_name, auto_initialize=True)
        except Exception as e:
            server_config = manual_call_template.config.mcpServers.get(server_name)
            is_stdio = isinstance(server_config, dict) and "command" in server_config
            if is_stdio and os.environ.get(CHILD_STDERR_ENV_VAR) != "inherit":
                self._log_error(
                    f"Failed to start stdio MCP server '{server_name}': {e}. The child's stderr was "
                    f"suppressed; re-run with {CHILD_STDERR_ENV_VAR}=inherit to see what it printed while starting."
                )
            raise

    async def _release_manual_client(self, manual_call_template: 'McpCallTemplate') -> None:
        """Drop this manual's claim on its client. The client's sessions are closed
        only when no manual references that configuration any more; two manuals
        with identical configurations share one client, and deregistering one
        must not tear down the other's sessions."""
        key = self._config_key(manual_call_template)
        manual_name = self._owner_key(manual_call_template, key)
        async with self._clients_lock:
            if self._manual_config_keys.get(manual_name) == key:
                del self._manual_config_keys[manual_name]
            if key in self._manual_config_keys.values():
                return
            client = self._mcp_clients.pop(key, None)
        if client is None:
            return
        try:
            await client.close_all_sessions()
            self._log_info(f"Closed the MCP client of manual '{manual_call_template.name}'")
        except Exception as e:
            # Keep it aside so close() can retry rather than leaking its processes;
            # never back into the live map, where a newer client for the same
            # configuration may already live.
            self._failed_clients.append(client)
            self._log_warning(f"Failed to close sessions of the MCP client of manual '{manual_call_template.name}': {e}")

    async def _cleanup_session(self, server_name: str, manual_call_template: 'McpCallTemplate'):
        """Clean up a specific session of the client serving this manual."""
        client = self._mcp_clients.get(self._config_key(manual_call_template))
        if client is not None and server_name in client.sessions:
            await client.close_session(server_name)
            self._log_info(f"Cleaned up session for server: {server_name}")

    async def _cleanup_all_sessions(self):
        """Close every session of every client. A client whose shutdown fails is
        kept so a later close() can retry it instead of leaking its processes."""
        for key, client in list(self._mcp_clients.items()):
            try:
                await client.close_all_sessions()
                del self._mcp_clients[key]
            except Exception as e:
                self._log_warning(f"Failed to close sessions of an MCP client: {e}")
        for client in list(self._failed_clients):
            try:
                await client.close_all_sessions()
                self._failed_clients.remove(client)
            except Exception as e:
                self._log_warning(f"Failed to close sessions of a previously failed MCP client: {e}")
        if not self._mcp_clients and not self._failed_clients:
            self._log_info("Cleaned up all sessions")

    def _add_server_to_tool_name(self, tools, server_name: str):
        """Prefix tool names with server name to ensure uniqueness."""
        for tool in tools:
            if not tool.name.startswith(f"{server_name}."):
                tool.name = f"{server_name}.{tool.name}"
                
        return tools

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
                await self._cleanup_session(server_name, manual_call_template)
                self._log_warning(f"Session-level error for list_tools, retrying with fresh session: {e}")
                
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
                self._log_error(f"Protocol-level error for list_tools: {e}")
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
            await self._cleanup_session(server_name, manual_call_template)
            self._log_warning(f"Session failed for list_resources, retrying: {e}")
            
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
            await self._cleanup_session(server_name, manual_call_template)
            self._log_warning(f"Session failed for read_resource '{resource_uri}', retrying: {e}")
            
            # Retry with a fresh session
            session = await self._get_or_create_session(server_name, manual_call_template)
            result = await session.read_resource(resource_uri)
            return result

    async def _call_tool_with_session(self, server_name: str, manual_call_template: 'McpCallTemplate', tool_name: str, inputs: Dict[str, Any]):
        """Call a tool using cached session when possible."""
        session = await self._get_or_create_session(server_name, manual_call_template)
        result = await session.call_tool(tool_name, arguments=inputs)
        return result

    @_with_owner
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
                    self._log_info(f"Discovering tools for server '{server_name}' via {server_config}")
                    mcp_tools = await self._list_tools_with_session(server_name, manual_call_template)
                    mcp_tools = self._add_server_to_tool_name(mcp_tools, server_name)
                    
                    self._log_info(f"Discovered {len(mcp_tools)} tools for server '{server_name}'")
                    for mcp_tool in mcp_tools:
                        # Convert mcp.Tool to utcp.data.tool.Tool
                        utcp_tool = Tool(
                            name=mcp_tool.name,
                            description=mcp_tool.description,
                            inputs=mcp_tool.inputSchema,
                            outputs=mcp_tool.outputSchema,
                            tool_call_template=manual_call_template
                        )
                        all_tools.append(utcp_tool)
                    
                    # Register resources as tools if enabled
                    if manual_call_template.register_resources_as_tools:
                        self._log_info(f"Discovering resources for server '{server_name}' to register as tools")
                        try:
                            mcp_resources = await self._list_resources_with_session(server_name, manual_call_template)
                            self._log_info(f"Discovered {len(mcp_resources)} resources for server '{server_name}'")
                            for mcp_resource in mcp_resources:
                                # Convert mcp.Resource to utcp.data.tool.Tool
                                # Create a tool that reads the resource when called
                                resource_tool = Tool(
                                    name=f"{server_name}.resource_{mcp_resource.name}",
                                    description=f"Read resource: {mcp_resource.description or mcp_resource.name}. URI: {mcp_resource.uri}",
                                    inputs={
                                        "type": "object",
                                        "properties": {},
                                        "required": []
                                    },
                                    outputs={
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
                            self._log_warning(f"Failed to discover resources for server '{server_name}': {resource_error}")
                            # Don't add this to errors since resources are optional
                            
                except Exception as e:
                    self._log_error(f"Failed to discover tools for server '{server_name}': {e}")
                    errors.append(f"Failed to discover tools for server '{server_name}': {e}")

        return RegisterManualResult(
            manual_call_template=manual_call_template,
            manual=UtcpManual(
                tools=all_tools
            ),
            success=len(errors) == 0,
            errors=errors
        )

    @_with_owner
    async def call_tool(self, caller: 'UtcpClient', tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        """REQUIRED
        Call a tool using the model context protocol.
        """
        if not isinstance(tool_call_template, McpCallTemplate):
            raise ValueError("tool_call_template must be a McpCallTemplate")
        if not tool_call_template.config or not tool_call_template.config.mcpServers:
            raise ValueError(f"No server configuration found for tool '{tool_name}'")
        
        parse_result = await self._parse_tool_name(tool_name, tool_call_template)

        if parse_result.is_resource:
            resource_name = parse_result.name
            server_name = parse_result.server_name
            target_resource = parse_result.target_resource

            try:
                # Read the resource
                self._log_info(f"Reading resource '{resource_name}' with URI '{target_resource.uri}' from server '{server_name}'")
                result = await self._read_resource_with_session(server_name, tool_call_template, target_resource.uri)
                
                # Process the result
                return result.model_dump()
            except Exception as e:
                self._log_error(f"Error reading resource '{resource_name}' on server '{server_name}': {e}")
                raise e
        else:
            tool_name = parse_result.name
            server_name = parse_result.server_name
                
            try:
                # Call the tool
                self._log_info(f"Call tool '{tool_name}' from server '{server_name}'")
                result = await self._call_tool_with_session(server_name, tool_call_template, tool_name, tool_args)
                
                # Process the result
                return self._process_tool_result(result, tool_name)
            except Exception as e:
                self._log_error(f"Error calling tool '{tool_name}' on server '{server_name}': {e}")
                raise e
    
    class _ParseToolResult:
        def __init__(self, manual_name: Optional[str], server_name: str, name: str, is_resource: bool, target_resource: Any):
            self.manual_name = manual_name
            self.server_name = server_name
            self.name = name
            self.is_resource = is_resource
            self.target_resource = target_resource
    
    async def _parse_tool_name(self, tool_name: str, tool_call_template: McpCallTemplate) -> _ParseToolResult:
        def normalize(val):
            if isinstance(val, tuple):
                return val
            return (val, None)

        if "." not in tool_name:
            is_resource, name = self._is_resource(tool_name)
            server_name, target_resource = normalize(await self._get_tool_server(name, tool_call_template) if not is_resource else await self._get_resource_server(name, tool_call_template))
            return McpCommunicationProtocol._ParseToolResult(None, server_name, name, is_resource, target_resource)
        
        split = tool_name.split(".", 1)
        manual_name = split[0]
        tool_name = split[1]
        
        if "." not in tool_name:
            is_resource, name = self._is_resource(tool_name)
            server_name, target_resource = normalize(await self._get_tool_server(name, tool_call_template) if not is_resource else await self._get_resource_server(name, tool_call_template))
            return McpCommunicationProtocol._ParseToolResult(manual_name, server_name, name, is_resource, target_resource)
        
        split = tool_name.split(".", 1) 
        server_name = split[0]
        tool_name = split[1]

        is_resource, name = self._is_resource(tool_name)
        server_name, target_resource = normalize(await self._get_tool_server(name, tool_call_template) if not is_resource else await self._get_resource_server(name, tool_call_template))
        return McpCommunicationProtocol._ParseToolResult(manual_name, server_name, name, is_resource, target_resource)

    def _is_resource(self, tool_name) -> Tuple[bool, str]:
        resource_prefix = "resource_"
        resource_length = len(resource_prefix)

        if tool_name.startswith(resource_prefix):
            return True, tool_name[resource_length:]

        return False, tool_name
        
    async def _get_tool_server(self, tool_name: str, tool_call_template: McpCallTemplate) -> str:
        if "." in tool_name:
            split = tool_name.split(".", 1)
            server_name = split[0]
            tool_name = split[1]

            return server_name
        
        # Try each server until we find one that has the tool
        for server_name, server_config in tool_call_template.config.mcpServers.items():
            self._log_info(f"Attempting to call tool '{tool_name}' on server '{server_name}'")
            
            # First check if this server has the tool
            tools = await self._list_tools_with_session(server_name, tool_call_template)
            tool_names = [tool.name for tool in tools]
            
            if tool_name not in tool_names:
                self._log_info(f"Tool '{tool_name}' not found in server '{server_name}'")
                continue  # Try next server

            return server_name
        
        raise ValueError(f"Tool '{tool_name}' not found in any configured server")
    
    async def _get_resource_server(self, resource_name: str, tool_call_template: McpCallTemplate) -> Tuple[str, Any]:
        for server_name, server_config in tool_call_template.config.mcpServers.items():
            self._log_info(f"Attempting to find resource '{resource_name}' on server '{server_name}'")
            
            # List resources to find the one with matching name
            resources = await self._list_resources_with_session(server_name, tool_call_template)
            target_resource = None
            for resource in resources:
                if resource.name == resource_name:
                    target_resource = resource
                    break
            
            if target_resource is None:
                self._log_info(f"Resource '{resource_name}' not found in server '{server_name}'")
                continue  # Try next server

            return server_name, target_resource
            
        raise ValueError(f"Resource '{resource_name}' not found in any configured server") 

    async def call_tool_streaming(self, caller: 'UtcpClient', tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any, None]:
        """REQUIRED
        Streaming calls are not supported for MCP protocol, so we just call the tool and return the result as one item."""
        result = await self.call_tool(caller, tool_name, tool_args, tool_call_template)
        yield result

    def _process_tool_result(self, result, tool_name: str) -> Any:
        self._log_info(f"Processing tool result for '{tool_name}', type: {type(result)}")
        
        # Prefer structuredContent (MCP spec field) whenever the server sent it.
        structured = getattr(result, 'structuredContent', None)
        if structured is not None:
            self._log_info(f"Found structuredContent: {structured}")
            # FastMCP wraps NON-OBJECT returns (primitives, lists, None) as
            # {"result": value}; object returns are sent as-is. Unwrap exactly that
            # shape: a single "result" key whose value is not a dict. A single-key
            # {"result": {...}} is therefore a genuine object return and passes
            # through untouched, as does any dict with other keys. A genuine
            # {"result": <primitive or list>} return is indistinguishable from the
            # wrapper on the wire and is unwrapped too; that ambiguity is inherent
            # to the FastMCP convention.
            if (
                isinstance(structured, dict)
                and set(structured.keys()) == {"result"}
                and not isinstance(structured["result"], dict)
            ):
                return structured["result"]
            return structured
        
        # Process content if available (fallback)
        if hasattr(result, 'content'):
            content = result.content
            self._log_info(f"Content type: {type(content)}")
            
            # Handle list content
            if isinstance(content, list):
                self._log_info(f"Content is a list with {len(content)} items")
                
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
        
        # Handle dictionary with 'result' key
        if isinstance(result, dict) and 'result' in result:
            return result['result']
        
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

    @_with_owner
    async def deregister_manual(self, caller: 'UtcpClient', manual_call_template: CallTemplate) -> None:
        """Deregister an MCP manual and clean up associated sessions."""
        if not isinstance(manual_call_template, McpCallTemplate):
            self._log_info(f"Deregistering manual '{manual_call_template.name}' - not an MCP template")
            return
            
        self._log_info(f"Deregistering manual '{manual_call_template.name}' and cleaning up sessions")
        
        # Release this manual's claim on its client; the client's sessions are
        # closed only when no other manual shares that configuration.
        if manual_call_template.config and manual_call_template.config.mcpServers:
            await self._release_manual_client(manual_call_template)

    async def close(self) -> None:
        """Close all active sessions and clean up resources."""
        self._log_info("Closing MCP communication protocol and cleaning up all sessions")
        await self._cleanup_all_sessions()
        self._log_info("MCP communication protocol closed successfully")

    async def _handle_oauth2(self, auth_details: OAuth2Auth) -> str:
        """Return an OAuth2 access token, fetching it at most once per burst.

        Validates the token endpoint, serves a cached token when present, and
        coalesces concurrent first-time fetches for the same client so a burst of
        callers issues a single token request and shares its result. The fetch
        runs outside ``_clients_lock`` (so a slow token endpoint can't stall
        client creation), which is exactly why the coalescing is needed here.
        """
        # Validate the token endpoint before sending credentials to it, so a
        # manual cannot direct the operator's client secret at an arbitrary host.
        _ensure_secure_mcp_url(auth_details.token_url, context="MCP OAuth2 token URL")
        cache_key = self._oauth_cache_key(auth_details)

        # Return cached token if available.
        if cache_key in self._oauth_tokens:
            return self._oauth_tokens[cache_key]["access_token"]

        # Coalesce concurrent first-time fetches. The check-and-set below is
        # synchronous (no await between them), so exactly one task is created and
        # every other caller awaits it.
        task = self._oauth_inflight.get(cache_key)
        if task is None:
            task = asyncio.ensure_future(self._fetch_oauth2_token(auth_details))
            self._oauth_inflight[cache_key] = task
            task.add_done_callback(lambda _t, k=cache_key: self._oauth_inflight.pop(k, None))
        # Shield the shared task: awaiting a task directly propagates a waiter's
        # cancellation into the task, which would cancel the fetch for every other
        # waiter too. shield lets a cancelled waiter raise on its own while the
        # shared fetch runs to completion for the rest.
        return await asyncio.shield(task)

    async def _fetch_oauth2_token(self, auth_details: OAuth2Auth) -> str:
        """Perform the OAuth2 client-credentials request (body method, then Basic)."""
        client_id = auth_details.client_id
        cache_key = self._oauth_cache_key(auth_details)
        async with aiohttp.ClientSession() as session:
            # Method 1: Send credentials in the request body
            try:
                self._log_info(f"Attempting OAuth2 token fetch for '{client_id}' with credentials in body.")
                body_data = {
                    'grant_type': 'client_credentials',
                    'client_id': client_id,
                    'client_secret': auth_details.client_secret,
                    'scope': auth_details.scope
                }
                async with session.post(auth_details.token_url, data=body_data, allow_redirects=False) as response:
                    self._reject_token_redirect(response)
                    response.raise_for_status()
                    token_response = await response.json()
                    self._oauth_tokens[cache_key] = token_response
                    return token_response["access_token"]
            except aiohttp.ClientError as e:
                self._log_error(f"OAuth2 with credentials in body failed: {e}. Trying Basic Auth header.")
                
            # Method 2: Send credentials as Basic Auth header
            try:
                self._log_info(f"Attempting OAuth2 token fetch for '{client_id}' with Basic Auth header.")
                header_auth = AiohttpBasicAuth(client_id, auth_details.client_secret)
                header_data = {
                    'grant_type': 'client_credentials',
                    'scope': auth_details.scope
                }
                async with session.post(auth_details.token_url, data=header_data, auth=header_auth, allow_redirects=False) as response:
                    self._reject_token_redirect(response)
                    response.raise_for_status()
                    token_response = await response.json()
                    self._oauth_tokens[cache_key] = token_response
                    return token_response["access_token"]
            except aiohttp.ClientError as e:
                self._log_error(f"OAuth2 with Basic Auth header also failed: {e}")
                raise e

    @staticmethod
    def _reject_token_redirect(response: "aiohttp.ClientResponse") -> None:
        """Refuse a redirect from the OAuth2 token endpoint.

        Redirects are disabled on the token request, so a 3xx here would be a
        token endpoint trying to bounce the credential-bearing POST to another
        host. Fail instead of replaying ``client_id`` / ``client_secret`` there.
        """
        if 300 <= response.status < 400:
            raise aiohttp.ClientError(
                f"OAuth2 token endpoint returned a redirect ({response.status}); "
                "refusing to replay credentials to the redirect target."
            )
