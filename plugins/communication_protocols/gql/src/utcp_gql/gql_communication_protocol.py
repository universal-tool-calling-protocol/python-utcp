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

from utcp_gql.gql_call_template import GraphQLProvider

if TYPE_CHECKING:
    from utcp.utcp_client import UtcpClient


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
)

logger = logging.getLogger(__name__)


class GraphQLCommunicationProtocol(CommunicationProtocol):
    """GraphQL protocol implementation for UTCP 1.0.

    - Discovers tools via GraphQL schema introspection.
    - Executes per-call sessions using `gql` over HTTP(S).
    - Supports `ApiKeyAuth`, `BasicAuth`, and `OAuth2Auth`.
    - Enforces HTTPS or localhost for security.
    """

    def __init__(self) -> None:
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}

    def _enforce_https_or_localhost(self, url: str) -> None:
        if not (
            url.startswith("https://")
            or url.startswith("http://localhost")
            or url.startswith("http://127.0.0.1")
        ):
            raise ValueError(
                "Security error: URL must use HTTPS or start with 'http://localhost' or 'http://127.0.0.1'. "
                "Non-secure URLs are vulnerable to man-in-the-middle attacks. "
                f"Got: {url}."
            )

    async def _handle_oauth2(self, auth: OAuth2Auth) -> str:
        client_id = auth.client_id
        if client_id in self._oauth_tokens:
            return self._oauth_tokens[client_id]["access_token"]
        async with aiohttp.ClientSession() as session:
            data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": auth.client_secret,
                "scope": auth.scope,
            }
            async with session.post(auth.token_url, data=data) as resp:
                resp.raise_for_status()
                token_response = await resp.json()
                self._oauth_tokens[client_id] = token_response
                return token_response["access_token"]

    async def _prepare_headers(
        self, provider: GraphQLProvider, tool_args: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        headers: Dict[str, str] = provider.headers.copy() if provider.headers else {}
        if provider.auth:
            if isinstance(provider.auth, ApiKeyAuth):
                if provider.auth.api_key and provider.auth.location == "header":
                    headers[provider.auth.var_name] = provider.auth.api_key
            elif isinstance(provider.auth, BasicAuth):
                import base64

                userpass = f"{provider.auth.username}:{provider.auth.password}"
                headers["Authorization"] = "Basic " + base64.b64encode(userpass.encode()).decode()
            elif isinstance(provider.auth, OAuth2Auth):
                token = await self._handle_oauth2(provider.auth)
                headers["Authorization"] = f"Bearer {token}"

        # Map selected tool_args into headers if requested
        if tool_args and provider.header_fields:
            for field in provider.header_fields:
                if field in tool_args and isinstance(tool_args[field], str):
                    headers[field] = tool_args[field]

        return headers

    async def register_manual(
        self, caller: "UtcpClient", manual_call_template: CallTemplate
    ) -> RegisterManualResult:
        if not isinstance(manual_call_template, GraphQLProvider):
            raise ValueError("GraphQLCommunicationProtocol requires a GraphQLProvider call template")
        self._enforce_https_or_localhost(manual_call_template.url)

        try:
            headers = await self._prepare_headers(manual_call_template)
            transport = AIOHTTPTransport(url=manual_call_template.url, headers=headers)
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
        if not isinstance(tool_call_template, GraphQLProvider):
            raise ValueError("GraphQLCommunicationProtocol requires a GraphQLProvider call template")
        self._enforce_https_or_localhost(tool_call_template.url)

        headers = await self._prepare_headers(tool_call_template, tool_args)
        transport = AIOHTTPTransport(url=tool_call_template.url, headers=headers)
        async with GqlClient(transport=transport, fetch_schema_from_transport=True) as session:
            op_type = getattr(tool_call_template, "operation_type", "query")
            # Strip manual prefix if present (client prefixes at save time)
            base_tool_name = tool_name.split(".", 1)[-1] if "." in tool_name else tool_name
            # Filter out header fields from GraphQL variables; these are sent via HTTP headers
            header_fields = tool_call_template.header_fields or []
            filtered_args = {k: v for k, v in tool_args.items() if k not in header_fields}

            defs = []
            for k, v in filtered_args.items():
                if isinstance(v, bool):
                    t = "Boolean"
                elif isinstance(v, int) and not isinstance(v, bool):
                    t = "Int"
                elif isinstance(v, float):
                    t = "Float"
                else:
                    t = "String"
                defs.append(f"${k}: {t}")
            arg_str = ", ".join(defs)
            var_defs = f"({arg_str})" if arg_str else ""
            arg_pass = ", ".join(f"{k}: ${k}" for k in filtered_args.keys())
            arg_pass = f"({arg_pass})" if arg_pass else ""

            gql_str = f"{op_type} {var_defs} {{ {base_tool_name}{arg_pass} }}"
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
        if not isinstance(tool_call_template, GraphQLProvider):
            raise ValueError("GraphQLCommunicationProtocol requires a GraphQLProvider call template")
        if getattr(tool_call_template, "operation_type", "query") == "subscription":
            raise ValueError("GraphQL subscription streaming is not implemented")
        result = await self.call_tool(caller, tool_name, tool_args, tool_call_template)
        yield result

    async def close(self) -> None:
        self._oauth_tokens.clear()