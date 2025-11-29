import os
import sys
import types
import pytest


# Ensure plugin src is importable
PLUGIN_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
PLUGIN_SRC = os.path.abspath(PLUGIN_SRC)
if PLUGIN_SRC not in sys.path:
    sys.path.append(PLUGIN_SRC)

import utcp_gql
# Simplify imports: use the main module and assign local aliases
GraphQLProvider = utcp_gql.gql_call_template.GraphQLProvider
gql_module = utcp_gql.gql_communication_protocol

from utcp.data.utcp_manual import UtcpManual
from utcp.utcp_client import UtcpClient
from utcp.implementations.utcp_client_implementation import UtcpClientImplementation


class FakeSchema:
    def __init__(self):
        # Minimal field objects with descriptions
        self.query_type = types.SimpleNamespace(
            fields={
                "hello": types.SimpleNamespace(description="Returns greeting"),
            }
        )
        self.mutation_type = types.SimpleNamespace(
            fields={
                "add": types.SimpleNamespace(description="Adds numbers"),
            }
        )
        self.subscription_type = None


class FakeClientObj:
    def __init__(self):
        self.client = types.SimpleNamespace(schema=FakeSchema())

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, document, variable_values=None):
        # document is a gql query; we can base behavior on variable_values
        variable_values = variable_values or {}
        # Determine operation by presence of variables used
        if "hello" in str(document):
            name = variable_values.get("name", "")
            return {"hello": f"Hello {name}"}
        if "add" in str(document):
            a = int(variable_values.get("a", 0))
            b = int(variable_values.get("b", 0))
            return {"add": a + b}
        return {"ok": True}


class FakeTransport:
    def __init__(self, url: str, headers: dict | None = None):
        self.url = url
        self.headers = headers or {}


@pytest.mark.asyncio
async def test_graphql_register_and_call(monkeypatch):
    # Patch gql client/transport used by protocol to avoid needing a real server
    monkeypatch.setattr(gql_module, "GqlClient", lambda *args, **kwargs: FakeClientObj())
    monkeypatch.setattr(gql_module, "AIOHTTPTransport", FakeTransport)
    # Avoid real GraphQL parsing; pass-through document string to fake execute
    monkeypatch.setattr(gql_module, "gql_query", lambda s: s)

    # Register plugin (call_template serializer + protocol)
    utcp_gql.register()

    # Create protocol and manual call template
    protocol = gql_module.GraphQLCommunicationProtocol()
    provider = GraphQLProvider(
        name="mock_graph",
        call_template_type="graphql",
        url="http://localhost/graphql",
        operation_type="query",
        headers={"x-client": "utcp"},
        header_fields=["x-session-id"],
    )

    # Minimal UTCP client implementation for caller context
    client: UtcpClient = await UtcpClientImplementation.create()
    client.config.variables = {}

    # Register and discover tools
    reg = await protocol.register_manual(client, provider)
    assert reg.success is True
    assert isinstance(reg.manual, UtcpManual)
    tool_names = sorted(t.name for t in reg.manual.tools)
    assert "hello" in tool_names
    assert "add" in tool_names

    # Call hello
    res = await protocol.call_tool(client, "mock_graph.hello", {"name": "UTCP", "x-session-id": "abc"}, provider)
    assert res == {"hello": "Hello UTCP"}

    # Call add (mutation)
    provider.operation_type = "mutation"
    res2 = await protocol.call_tool(client, "mock_graph.add", {"a": 2, "b": 3}, provider)
    assert res2 == {"add": 5}