"""Integration tests for GraphQL communication protocol using real GraphQL servers.

Uses the public Countries API (https://countries.trevorblades.com/graphql) which
requires no authentication and has a stable schema.
"""
import os
import sys
import warnings
import pytest
import pytest_asyncio

# Ensure plugin src is importable
PLUGIN_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
PLUGIN_SRC = os.path.abspath(PLUGIN_SRC)
if PLUGIN_SRC not in sys.path:
    sys.path.append(PLUGIN_SRC)

import utcp_gql
from utcp_gql.gql_call_template import GraphQLCallTemplate
from utcp_gql.gql_communication_protocol import GraphQLCommunicationProtocol

from utcp.implementations.utcp_client_implementation import UtcpClientImplementation

# Public GraphQL API for testing (no auth required)
COUNTRIES_API_URL = "https://countries.trevorblades.com/graphql"

# Suppress gql SSL warning (we're using HTTPS which is secure)
warnings.filterwarnings("ignore", message=".*AIOHTTPTransport does not verify ssl.*")


@pytest.fixture
def protocol():
    """Create a fresh GraphQL protocol instance."""
    utcp_gql.register()
    return GraphQLCommunicationProtocol()


@pytest_asyncio.fixture
async def client():
    """Create a minimal UTCP client."""
    return await UtcpClientImplementation.create()


@pytest.mark.asyncio
async def test_register_manual_discovers_tools(protocol, client):
    """Test that register_manual discovers tools from a real GraphQL schema."""
    template = GraphQLCallTemplate(
        name="countries_api",
        url=COUNTRIES_API_URL,
    )

    result = await protocol.register_manual(client, template)

    assert result.success is True
    assert len(result.manual.tools) > 0

    # The Countries API should have these common queries
    tool_names = [t.name for t in result.manual.tools]
    assert "countries" in tool_names or "country" in tool_names


@pytest.mark.asyncio
async def test_call_tool_with_custom_query(protocol, client):
    """Test calling a tool with a custom query string (fixes selection set issue)."""
    # Custom query with proper selection set - this is the UTCP-flexible approach
    custom_query = """
    query GetCountry($code: ID!) {
        country(code: $code) {
            name
            capital
            currency
        }
    }
    """

    template = GraphQLCallTemplate(
        name="countries_api",
        url=COUNTRIES_API_URL,
        query=custom_query,
    )

    result = await protocol.call_tool(
        client,
        "country",
        {"code": "US"},
        template,
    )

    assert result is not None
    assert "country" in result
    assert result["country"]["name"] == "United States"
    assert result["country"]["capital"] == "Washington D.C."


@pytest.mark.asyncio
async def test_call_tool_with_variable_types(protocol, client):
    """Test that variable_types properly maps GraphQL types (fixes String-only issue)."""
    # The country query expects code: ID!, not String
    # Using variable_types to specify the correct type
    custom_query = """
    query GetCountry($code: ID!) {
        country(code: $code) {
            name
            emoji
        }
    }
    """

    template = GraphQLCallTemplate(
        name="countries_api",
        url=COUNTRIES_API_URL,
        query=custom_query,
        variable_types={"code": "ID!"},
    )

    result = await protocol.call_tool(
        client,
        "country",
        {"code": "FR"},
        template,
    )

    assert result is not None
    assert result["country"]["name"] == "France"
    assert result["country"]["emoji"] == "🇫🇷"


@pytest.mark.asyncio
async def test_call_tool_list_query(protocol, client):
    """Test querying a list of items with proper selection set."""
    custom_query = """
    query GetContinents {
        continents {
            code
            name
        }
    }
    """

    template = GraphQLCallTemplate(
        name="countries_api",
        url=COUNTRIES_API_URL,
        query=custom_query,
    )

    result = await protocol.call_tool(
        client,
        "continents",
        {},
        template,
    )

    assert result is not None
    assert "continents" in result
    assert len(result["continents"]) == 7  # 7 continents

    continent_names = [c["name"] for c in result["continents"]]
    assert "Europe" in continent_names
    assert "Asia" in continent_names


@pytest.mark.asyncio
async def test_call_tool_nested_query(protocol, client):
    """Test querying nested objects with proper selection sets."""
    custom_query = """
    query GetCountryWithLanguages($code: ID!) {
        country(code: $code) {
            name
            languages {
                code
                name
            }
        }
    }
    """

    template = GraphQLCallTemplate(
        name="countries_api",
        url=COUNTRIES_API_URL,
        query=custom_query,
    )

    result = await protocol.call_tool(
        client,
        "country",
        {"code": "CH"},  # Switzerland - has multiple languages
        template,
    )

    assert result is not None
    assert result["country"]["name"] == "Switzerland"
    assert len(result["country"]["languages"]) >= 3  # German, French, Italian, Romansh


@pytest.mark.asyncio
async def test_call_tool_with_filter_arguments(protocol, client):
    """Test queries with filter arguments using proper types."""
    custom_query = """
    query GetCountriesByContinent($filter: CountryFilterInput) {
        countries(filter: $filter) {
            code
            name
        }
    }
    """

    template = GraphQLCallTemplate(
        name="countries_api",
        url=COUNTRIES_API_URL,
        query=custom_query,
        variable_types={"filter": "CountryFilterInput"},
    )

    result = await protocol.call_tool(
        client,
        "countries",
        {"filter": {"continent": {"eq": "EU"}}},
        template,
    )

    assert result is not None
    assert "countries" in result
    # Should return European countries
    country_codes = [c["code"] for c in result["countries"]]
    assert "DE" in country_codes  # Germany
    assert "FR" in country_codes  # France


@pytest.mark.asyncio
async def test_error_handling_invalid_query(protocol, client):
    """Test that invalid queries return proper errors."""
    # Invalid query syntax
    invalid_query = "this is not valid graphql"

    template = GraphQLCallTemplate(
        name="countries_api",
        url=COUNTRIES_API_URL,
        query=invalid_query,
    )

    with pytest.raises(Exception):
        await protocol.call_tool(
            client,
            "invalid",
            {},
            template,
        )


@pytest.mark.asyncio
async def test_error_handling_missing_selection_set_auto_generated(protocol, client):
    """
    Demonstrate that auto-generated queries fail for object-returning fields.
    
    This test documents the limitation: without a custom query, object fields fail.
    The fix is to always use the `query` field for object-returning operations.
    """
    # No custom query - will auto-generate without selection set
    template = GraphQLCallTemplate(
        name="countries_api",
        url=COUNTRIES_API_URL,
        operation_type="query",
        variable_types={"code": "ID!"},
    )

    # This should fail because auto-generated query lacks selection set
    # The query becomes: query ($code: ID!) { country(code: $code) }
    # But country returns an object that needs: { name capital ... }
    with pytest.raises(Exception):
        await protocol.call_tool(
            client,
            "country",
            {"code": "US"},
            template,
        )
