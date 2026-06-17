import logging
from typing import Dict, Any, List, Optional, AsyncGenerator, TYPE_CHECKING

import aiohttp
from gql import Client as GqlClient, gql as gql_query
from gql.transport.aiohttp import AIOHTTPTransport

from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool, JsonSchema
from utcp.data.utcp_manual import UtcpManual
from utcp.data.register_manual_response import RegisterManualResult
from utcp.data.auth_implementations.api_key_auth import ApiKeyAuth
from utcp.data.auth_implementations.basic_auth import BasicAuth
from utcp.data.auth_implementations.oauth2_auth import OAuth2Auth

from utcp_gql.gql_call_template import GraphQLCallTemplate
from utcp_gql._security import ensure_secure_url, safe_request_with_redirects

if TYPE_CHECKING:
    from utcp.utcp_client import UtcpClient


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
)

logger = logging.getLogger(__name__)


class _SecureAIOHTTPTransport(AIOHTTPTransport):
    """``AIOHTTPTransport`` subclass that patches the underlying
    aiohttp ``ClientSession`` to refuse redirects as soon as it is
    created during ``connect()``.

    The previous fix patched the session AFTER entering the
    ``GqlClient`` context, but when ``fetch_schema_from_transport=
    True`` the schema introspection request is issued inside the
    ``GqlClient.__aenter__`` call -- BEFORE the patch could land.
    That left the very first GraphQL request unprotected and
    re-introduced the redirect-SSRF / credential-leak window.
    Patching inside ``connect()`` guarantees every outbound POST
    from this transport (introspection included) skips redirects.
    """

    async def connect(self) -> None:  # type: ignore[override]
        await super().connect()
        session = getattr(self, "session", None)
        if session is None:
            return
        original_post = session.post

        def _no_redirect_post(*args: Any, **kwargs: Any):
            kwargs["allow_redirects"] = False
            return original_post(*args, **kwargs)

        session.post = _no_redirect_post  # type: ignore[method-assign]


class GraphQLCommunicationProtocol(CommunicationProtocol):
    """GraphQL protocol implementation for UTCP 1.0.

    - Discovers tools via GraphQL schema introspection.
    - Executes per-call sessions using `gql` over HTTP(S).
    - Supports `ApiKeyAuth`, `BasicAuth`, and `OAuth2Auth`.
    - Enforces HTTPS or localhost for security.
    """

    def __init__(self) -> None:
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}

    async def _handle_oauth2(self, auth: OAuth2Auth) -> str:
        """Fetch an OAuth2 access token.

        Validates the token URL with the hostname-based ``ensure_secure_url``
        helper before any credential bytes leave the process, and follows
        redirects only after re-validating each hop -- defends against the
        sibling SSRF / credential-exfiltration patterns in
        GHSA-8cp3-qxj6-px34 and GHSA-9qhg-99ww-9mqc.
        """
        client_id = auth.client_id
        if client_id in self._oauth_tokens:
            return self._oauth_tokens[client_id]["access_token"]

        ensure_secure_url(auth.token_url, context="OAuth2 token URL")

        async with aiohttp.ClientSession() as session:
            data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": auth.client_secret,
                "scope": auth.scope,
            }
            async with safe_request_with_redirects(
                session,
                "POST",
                auth.token_url,
                context="OAuth2 token fetch",
                data=data,
            ) as resp:
                resp.raise_for_status()
                token_response = await resp.json()
                self._oauth_tokens[client_id] = token_response
                return token_response["access_token"]

    async def _prepare_headers(
        self, call_template: GraphQLCallTemplate, tool_args: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        headers: Dict[str, str] = call_template.headers.copy() if call_template.headers else {}
        if call_template.auth:
            if isinstance(call_template.auth, ApiKeyAuth):
                if call_template.auth.api_key and call_template.auth.location == "header":
                    headers[call_template.auth.var_name] = call_template.auth.api_key
            elif isinstance(call_template.auth, BasicAuth):
                import base64

                userpass = f"{call_template.auth.username}:{call_template.auth.password}"
                headers["Authorization"] = "Basic " + base64.b64encode(userpass.encode()).decode()
            elif isinstance(call_template.auth, OAuth2Auth):
                token = await self._handle_oauth2(call_template.auth)
                headers["Authorization"] = f"Bearer {token}"

        # Map selected tool_args into headers if requested
        if tool_args and call_template.header_fields:
            for field in call_template.header_fields:
                if field in tool_args and isinstance(tool_args[field], str):
                    headers[field] = tool_args[field]

        return headers

    async def register_manual(
        self, caller: "UtcpClient", manual_call_template: CallTemplate
    ) -> RegisterManualResult:
        if not isinstance(manual_call_template, GraphQLCallTemplate):
            raise ValueError("GraphQLCommunicationProtocol requires a GraphQLCallTemplate call template")
        # Hostname-based validation -- replaces the broken ``startswith``
        # prefix check that let ``http://127.0.0.1.attacker.example``
        # through (GHSA-ppx3-28rw-8fpf).
        ensure_secure_url(
            manual_call_template.url, context="GraphQL manual discovery"
        )

        try:
            headers = await self._prepare_headers(manual_call_template)
            transport = _SecureAIOHTTPTransport(url=manual_call_template.url, headers=headers)
            async with GqlClient(transport=transport, fetch_schema_from_transport=True) as session:
                schema = session.client.schema
                tools: List[Tool] = []

                # Queries
                if hasattr(schema, "query_type") and schema.query_type:
                    for name, field in schema.query_type.fields.items():
                        tools.append(
                            Tool(
                                name=name,
                                description=getattr(field, "description", "") or "",
                                inputs=JsonSchema(type="object"),
                                outputs=JsonSchema(type="object"),
                                tool_call_template=manual_call_template,
                            )
                        )

                # Mutations
                if hasattr(schema, "mutation_type") and schema.mutation_type:
                    for name, field in schema.mutation_type.fields.items():
                        tools.append(
                            Tool(
                                name=name,
                                description=getattr(field, "description", "") or "",
                                inputs=JsonSchema(type="object"),
                                outputs=JsonSchema(type="object"),
                                tool_call_template=manual_call_template,
                            )
                        )

                # Subscriptions (listed for completeness)
                if hasattr(schema, "subscription_type") and schema.subscription_type:
                    for name, field in schema.subscription_type.fields.items():
                        tools.append(
                            Tool(
                                name=name,
                                description=getattr(field, "description", "") or "",
                                inputs=JsonSchema(type="object"),
                                outputs=JsonSchema(type="object"),
                                tool_call_template=manual_call_template,
                            )
                        )

                manual = UtcpManual(tools=tools)
                return RegisterManualResult(
                    manual_call_template=manual_call_template,
                    manual=manual,
                    success=True,
                    errors=[],
                )
        except Exception as e:
            logger.error(f"GraphQL manual registration failed for '{manual_call_template.name}': {e}")
            return RegisterManualResult(
                manual_call_template=manual_call_template,
                manual=UtcpManual(manual_version="0.0.0", tools=[]),
                success=False,
                errors=[str(e)],
            )

    async def deregister_manual(
        self, caller: "UtcpClient", manual_call_template: CallTemplate
    ) -> None:
        # Stateless: nothing to clean up
        return None

    async def call_tool(
        self,
        caller: "UtcpClient",
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_call_template: CallTemplate,
    ) -> Any:
        if not isinstance(tool_call_template, GraphQLCallTemplate):
            raise ValueError("GraphQLCommunicationProtocol requires a GraphQLCallTemplate call template")
        ensure_secure_url(
            tool_call_template.url, context="GraphQL tool invocation"
        )

        headers = await self._prepare_headers(tool_call_template, tool_args)
        transport = _SecureAIOHTTPTransport(url=tool_call_template.url, headers=headers)
        async with GqlClient(transport=transport, fetch_schema_from_transport=True) as session:
            # Filter out header fields from GraphQL variables; these are sent via HTTP headers
            header_fields = tool_call_template.header_fields or []
            filtered_args = {k: v for k, v in tool_args.items() if k not in header_fields}

            # Use custom query if provided (highest flexibility for agents)
            if tool_call_template.query:
                gql_str = tool_call_template.query
            else:
                # Auto-generate query - use variable_types for proper typing
                op_type = getattr(tool_call_template, "operation_type", "query")
                base_tool_name = tool_name.split(".", 1)[-1] if "." in tool_name else tool_name
                variable_types = tool_call_template.variable_types or {}

                # Build variable definitions with proper types (default to String)
                arg_str = ", ".join(
                    f"${k}: {variable_types.get(k, 'String')}"
                    for k in filtered_args.keys()
                )
                var_defs = f"({arg_str})" if arg_str else ""
                arg_pass = ", ".join(f"{k}: ${k}" for k in filtered_args.keys())
                arg_pass = f"({arg_pass})" if arg_pass else ""

                # Note: Auto-generated queries for object-returning fields will still fail
                # without a selection set. Use the `query` field for full control.
                gql_str = f"{op_type} {var_defs} {{ {base_tool_name}{arg_pass} }}"
                logger.debug(f"Auto-generated GraphQL: {gql_str}")

            document = gql_query(gql_str)
            result = await session.execute(document, variable_values=filtered_args)
            return result

    async def call_tool_streaming(
        self,
        caller: "UtcpClient",
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_call_template: CallTemplate,
    ) -> AsyncGenerator[Any, None]:
        # Basic implementation: execute non-streaming and yield once
        result = await self.call_tool(caller, tool_name, tool_args, tool_call_template)
        yield result

    async def close(self) -> None:
        self._oauth_tokens.clear()