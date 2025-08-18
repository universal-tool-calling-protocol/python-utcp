# import pytest
# import pytest_asyncio
# import json
# from aiohttp import web
# from utcp.client.transport_interfaces.graphql_transport import GraphQLClientTransport
# from utcp.shared.provider import GraphQLProvider
# from utcp.shared.auth import ApiKeyAuth, BasicAuth, OAuth2Auth


# @pytest_asyncio.fixture
# async def graphql_app():
#     async def graphql_handler(request):
#         body = await request.json()
#         query = body.get("query", "")
#         variables = body.get("variables", {})
#         # Introspection query (minimal response)
#         if "__schema" in query:
#             return web.json_response({
#                 "data": {
#                     "__schema": {
#                         "queryType": {"name": "Query"},
#                         "mutationType": {"name": "Mutation"},
#                         "subscriptionType": None,
#                         "types": [
#                             {"kind": "OBJECT", "name": "Query", "fields": [
#                                 {"name": "hello", "args": [{"name": "name", "type": {"kind": "SCALAR", "name": "String"}, "defaultValue": None}], "type": {"kind": "SCALAR", "name": "String"}, "isDeprecated": False, "deprecationReason": None}
#                             ], "interfaces": []},
#                             {"kind": "OBJECT", "name": "Mutation", "fields": [
#                                 {"name": "add", "args": [
#                                     {"name": "a", "type": {"kind": "SCALAR", "name": "Int"}, "defaultValue": None},
#                                     {"name": "b", "type": {"kind": "SCALAR", "name": "Int"}, "defaultValue": None}
#                                 ], "type": {"kind": "SCALAR", "name": "Int"}, "isDeprecated": False, "deprecationReason": None}
#                             ], "interfaces": []},
#                             {"kind": "SCALAR", "name": "String"},
#                             {"kind": "SCALAR", "name": "Int"},
#                             {"kind": "SCALAR", "name": "Boolean"}
#                         ],
#                         "directives": []
#                     }
#                 }
#             })
#         # hello query
#         if "hello" in query:
#             name = variables.get("name", "world")
#             return web.json_response({"data": {"hello": f"Hello, {name}!"}})
#         # add mutation
#         if "add" in query:
#             a = variables.get("a", 0)
#             b = variables.get("b", 0)
#             return web.json_response({"data": {"add": a + b}})
#         # fallback
#         return web.json_response({"data": {}}, status=200)

#     app = web.Application()
#     app.router.add_post("/graphql", graphql_handler)
#     return app

# @pytest_asyncio.fixture
# async def aiohttp_graphql_client(aiohttp_client, graphql_app):
#     return await aiohttp_client(graphql_app)

# @pytest_asyncio.fixture
# def transport():
#     return GraphQLClientTransport()

# @pytest_asyncio.fixture
# def provider(aiohttp_graphql_client):
#     return GraphQLProvider(
#         name="test-graphql-provider",
#         url=str(aiohttp_graphql_client.make_url("/graphql")),
#         headers={},
#     )

# @pytest.mark.asyncio
# async def test_register_tool_provider_discovers_tools(transport, provider):
#     tools = await transport.register_tool_provider(provider)
#     tool_names = [tool.name for tool in tools]
#     assert "hello" in tool_names
#     assert "add" in tool_names

# @pytest.mark.asyncio
# async def test_call_tool_query(transport, provider):
#     result = await transport.call_tool("hello", {"name": "Alice"}, provider)
#     assert result["hello"] == "Hello, Alice!"

# @pytest.mark.asyncio
# async def test_call_tool_mutation(transport, provider):
#     provider.operation_type = "mutation"
#     mutation = '''
#     mutation ($a: Int, $b: Int) {
#         add(a: $a, b: $b)
#     }
#     '''
#     result = await transport.call_tool("add", {"a": 2, "b": 3}, provider, query=mutation)
#     assert result["add"] == 5

# @pytest.mark.asyncio
# async def test_call_tool_api_key(transport, provider):
#     provider.headers = {}
#     provider.auth = ApiKeyAuth(var_name="X-API-Key", api_key="test-key")
#     result = await transport.call_tool("hello", {"name": "Bob"}, provider)
#     assert result["hello"] == "Hello, Bob!"

# @pytest.mark.asyncio
# async def test_call_tool_basic_auth(transport, provider):
#     provider.headers = {}
#     provider.auth = BasicAuth(username="user", password="pass")
#     result = await transport.call_tool("hello", {"name": "Eve"}, provider)
#     assert result["hello"] == "Hello, Eve!"

# @pytest.mark.asyncio
# async def test_call_tool_oauth2(monkeypatch, transport, provider):
#     async def fake_oauth2(auth):
#         return "fake-token"
#     transport._handle_oauth2 = fake_oauth2
#     provider.headers = {}
#     provider.auth = OAuth2Auth(token_url="http://fake/token", client_id="id", client_secret="secret", scope="scope")
#     result = await transport.call_tool("hello", {"name": "Zoe"}, provider)
#     assert result["hello"] == "Hello, Zoe!"

# @pytest.mark.asyncio
# async def test_enforce_https_or_localhost_raises(transport, provider):
#     provider.url = "http://evil.com/graphql"
#     with pytest.raises(ValueError):
#         await transport.call_tool("hello", {"name": "Mallory"}, provider)

# @pytest.mark.asyncio
# async def test_deregister_tool_provider_noop(transport, provider):
#     await transport.deregister_tool_provider(provider) 