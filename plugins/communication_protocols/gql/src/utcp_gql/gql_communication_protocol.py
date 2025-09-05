import sys
from typing import Dict, Any, List, Optional, Callable
import aiohttp
import asyncio
import ssl
from gql import Client as GqlClient, gql as gql_query
from gql.transport.aiohttp import AIOHTTPTransport
from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.shared.provider import Provider, GraphQLProvider
from utcp.shared.tool import Tool, ToolInputOutputSchema
from utcp.shared.auth import ApiKeyAuth, BasicAuth, OAuth2Auth
import logging

logger = logging.getLogger(__name__)

if not logger.hasHandlers():  # Only add default handler if user didn't configure logging
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class GraphQLClientTransport(ClientTransportInterface):
    """
    Simple, robust, production-ready GraphQL transport using gql.
    Stateless, per-operation. Supports all GraphQL features.
    """
    def __init__(self):
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}

    def _enforce_https_or_localhost(self, url: str):
        if not (url.startswith("https://") or url.startswith("http://localhost") or url.startswith("http://127.0.0.1")):
            raise ValueError(
                f"Security error: URL must use HTTPS or start with 'http://localhost' or 'http://127.0.0.1'. Got: {url}. "
                "Non-secure URLs are vulnerable to man-in-the-middle attacks."
            )

    async def _handle_oauth2(self, auth: OAuth2Auth) -> str:
        client_id = auth.client_id
        if client_id in self._oauth_tokens:
            return self._oauth_tokens[client_id]["access_token"]
        async with aiohttp.ClientSession() as session:
            data = {
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': auth.client_secret,
                'scope': auth.scope
            }
            async with session.post(auth.token_url, data=data) as resp:
                resp.raise_for_status()
                token_response = await resp.json()
                self._oauth_tokens[client_id] = token_response
                return token_response["access_token"]

    async def _prepare_headers(self, provider: GraphQLProvider) -> Dict[str, str]:
        headers = provider.headers.copy() if provider.headers else {}
        if provider.auth:
            if isinstance(provider.auth, ApiKeyAuth):
                if provider.auth.api_key:
                    if provider.auth.location == "header":
                        headers[provider.auth.var_name] = provider.auth.api_key
                # (query/cookie not supported for GraphQL by default)
            elif isinstance(provider.auth, BasicAuth):
                import base64
                userpass = f"{provider.auth.username}:{provider.auth.password}"
                headers["Authorization"] = "Basic " + base64.b64encode(userpass.encode()).decode()
            elif isinstance(provider.auth, OAuth2Auth):
                token = await self._handle_oauth2(provider.auth)
                headers["Authorization"] = f"Bearer {token}"
        return headers

    async def register_tool_provider(self, manual_provider: Provider) -> List[Tool]:
        if not isinstance(manual_provider, GraphQLProvider):
            raise ValueError("GraphQLClientTransport can only be used with GraphQLProvider")
        self._enforce_https_or_localhost(manual_provider.url)
        headers = await self._prepare_headers(manual_provider)
        transport = AIOHTTPTransport(url=manual_provider.url, headers=headers)
        async with GqlClient(transport=transport, fetch_schema_from_transport=True) as session:
            schema = session.client.schema
            tools = []
            # Queries
            if hasattr(schema, 'query_type') and schema.query_type:
                for name, field in schema.query_type.fields.items():
                    tools.append(Tool(
                        name=name,
                        description=getattr(field, 'description', '') or '',
                        inputs=ToolInputOutputSchema(required=None),
                        tool_provider=manual_provider
                    ))
            # Mutations
            if hasattr(schema, 'mutation_type') and schema.mutation_type:
                for name, field in schema.mutation_type.fields.items():
                    tools.append(Tool(
                        name=name,
                        description=getattr(field, 'description', '') or '',
                        inputs=ToolInputOutputSchema(required=None),
                        tool_provider=manual_provider
                    ))
            # Subscriptions (listed, but not called here)
            if hasattr(schema, 'subscription_type') and schema.subscription_type:
                for name, field in schema.subscription_type.fields.items():
                    tools.append(Tool(
                        name=name,
                        description=getattr(field, 'description', '') or '',
                        inputs=ToolInputOutputSchema(required=None),
                        tool_provider=manual_provider
                    ))
            return tools

    async def deregister_tool_provider(self, manual_provider: Provider) -> None:
        # Stateless: nothing to do
        pass

    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any], tool_provider: Provider, query: Optional[str] = None) -> Any:
        if not isinstance(tool_provider, GraphQLProvider):
            raise ValueError("GraphQLClientTransport can only be used with GraphQLProvider")
        self._enforce_https_or_localhost(tool_provider.url)
        headers = await self._prepare_headers(tool_provider)
        transport = AIOHTTPTransport(url=tool_provider.url, headers=headers)
        async with GqlClient(transport=transport, fetch_schema_from_transport=True) as session:
            if query is not None:
                document = gql_query(query)
                result = await session.execute(document, variable_values=tool_args)
                return result
            # If no query provided, build a simple query
            # Default to query operation
            op_type = getattr(tool_provider, 'operation_type', 'query')
            arg_str = ', '.join(f"${k}: String" for k in tool_args.keys())
            var_defs = f"({arg_str})" if arg_str else ""
            arg_pass = ', '.join(f"{k}: ${k}" for k in tool_args.keys())
            arg_pass = f"({arg_pass})" if arg_pass else ""
            gql_str = f"{op_type} {var_defs} {{ {tool_name}{arg_pass} }}"
            document = gql_query(gql_str)
            result = await session.execute(document, variable_values=tool_args)
            return result

    async def close(self) -> None:
        self._oauth_tokens.clear()
