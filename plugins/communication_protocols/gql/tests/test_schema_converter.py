"""Unit tests for the GraphQL to JSON Schema converter and selection set generator.

These tests run completely offline and mock GraphQL schemas using graphql-core.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pydantic import ValidationError
from graphql import (
    GraphQLArgument,
    GraphQLEnumType,
    GraphQLEnumValue,
    GraphQLField,
    GraphQLFloat,
    GraphQLID,
    GraphQLInputField,
    GraphQLInputObjectType,
    GraphQLInt,
    GraphQLList,
    GraphQLNonNull,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLSchema,
    GraphQLString,
    GraphQLUnionType,
)

from utcp_gql.gql_call_template import GraphQLCallTemplate
from utcp_gql.gql_communication_protocol import GraphQLCommunicationProtocol
from utcp_gql.schema_converter import (
    convert_field_args_to_input_schema,
    convert_field_output_to_output_schema,
    convert_graphql_type_to_json_schema,
    format_graphql_type_string,
    generate_default_selection_set,
)


def test_convert_scalar_types():
    """Verify standard and custom scalars map to appropriate JSON Schema types with nullability."""
    str_schema = convert_graphql_type_to_json_schema(GraphQLString, description="A string")
    assert str_schema.type == ["string", "null"]
    assert str_schema.description == "A string"

    int_schema = convert_graphql_type_to_json_schema(GraphQLInt, default_value=42)
    assert int_schema.type == ["integer", "null"]
    assert int_schema.default == 42

    float_schema = convert_graphql_type_to_json_schema(GraphQLFloat)
    assert float_schema.type == ["number", "null"]

    id_schema = convert_graphql_type_to_json_schema(GraphQLID)
    assert id_schema.type == ["string", "null"]
    assert "identifier" in (id_schema.description or "").lower()

    # Custom scalar
    date_scalar = GraphQLScalarType(name="DateTime", description="ISO timestamp")
    dt_schema = convert_graphql_type_to_json_schema(date_scalar)
    assert dt_schema.type == ["string", "null"]
    assert dt_schema.format == "date-time"


def test_convert_non_null_type():
    """Verify NonNull unwraps to the inner type and removes null from type."""
    non_null_str = GraphQLNonNull(GraphQLString)
    schema = convert_graphql_type_to_json_schema(non_null_str)
    assert schema.type == "string"


def test_convert_list_type():
    """Verify GraphQLList maps to an array schema with items, preserving nullability."""
    list_of_ints = GraphQLList(GraphQLInt)
    schema = convert_graphql_type_to_json_schema(list_of_ints)
    assert schema.type == ["array", "null"]
    assert schema.items is not None
    assert schema.items.type == ["integer", "null"]

    # NonNull wrapper on list and elements
    nn_list = GraphQLNonNull(GraphQLList(GraphQLNonNull(GraphQLInt)))
    nn_schema = convert_graphql_type_to_json_schema(nn_list)
    assert nn_schema.type == "array"
    assert nn_schema.items is not None
    assert nn_schema.items.type == "integer"


def test_convert_enum_type():
    """Verify GraphQLEnumType maps to a string with enum values and nullability."""
    role_enum = GraphQLEnumType(
        "Role",
        {
            "ADMIN": GraphQLEnumValue(description="Administrator"),
            "USER": GraphQLEnumValue(description="Regular user"),
            "GUEST": GraphQLEnumValue(description="Guest"),
        },
    )
    schema = convert_graphql_type_to_json_schema(role_enum)
    assert schema.type == ["string", "null"]
    assert schema.enum == ["ADMIN", "USER", "GUEST"]

    # Non-null enum
    schema_nn = convert_graphql_type_to_json_schema(GraphQLNonNull(role_enum))
    assert schema_nn.type == "string"
    assert schema_nn.enum == ["ADMIN", "USER", "GUEST"]


def test_convert_input_object_with_required_fields():
    """Verify GraphQLInputObjectType maps to an object schema with properties and required fields."""
    user_input = GraphQLInputObjectType(
        "UserInput",
        {
            "username": GraphQLInputField(GraphQLNonNull(GraphQLString), description="User handle"),
            "age": GraphQLInputField(GraphQLInt, default_value=18),
            "tags": GraphQLInputField(GraphQLList(GraphQLString)),
        },
    )
    schema = convert_graphql_type_to_json_schema(user_input)
    assert schema.type == ["object", "null"]
    assert schema.properties is not None
    assert "username" in schema.properties
    assert schema.properties["username"].type == "string"
    assert "age" in schema.properties
    assert schema.properties["age"].type == ["integer", "null"]
    assert schema.properties["age"].default == 18
    assert "tags" in schema.properties
    assert schema.properties["tags"].type == ["array", "null"]
    assert schema.required == ["username"]


def test_convert_input_object_cycle_protection():
    """Verify recursive input objects do not trigger infinite recursion and cut off properties."""
    node_input = GraphQLInputObjectType(
        "NodeInput",
        lambda: {
            "name": GraphQLInputField(GraphQLString),
            "parent": GraphQLInputField(node_input),
        },
    )
    schema = convert_graphql_type_to_json_schema(node_input, max_depth=2)
    assert schema.type == ["object", "null"]
    assert schema.properties is not None
    assert "name" in schema.properties
    assert "parent" in schema.properties
    assert schema.properties["parent"].type == ["object", "null"]
    # Reaching depth limit or revisited node must cut off recursion: revisited parent has no properties
    assert schema.properties["parent"].properties is None


def test_convert_field_args_to_input_schema():
    """Verify field arguments are converted to UTCP inputs schema."""
    field = GraphQLField(
        GraphQLString,
        args={
            "id": GraphQLArgument(GraphQLNonNull(GraphQLID), description="The entity ID"),
            "limit": GraphQLArgument(GraphQLInt, default_value=10, description="Max results"),
        },
    )
    schema = convert_field_args_to_input_schema(field)
    assert schema.type == "object"
    assert schema.properties is not None
    assert "id" in schema.properties
    assert schema.properties["id"].type == "string"
    assert schema.properties["id"].description == "The entity ID"
    assert "limit" in schema.properties
    assert schema.properties["limit"].type == ["integer", "null"]
    assert schema.properties["limit"].default == 10
    assert schema.required == ["id"]


def test_convert_field_output_to_output_schema():
    """Verify field return type maps to output schema."""
    person_type = GraphQLObjectType(
        "Person",
        {
            "id": GraphQLField(GraphQLNonNull(GraphQLID)),
            "name": GraphQLField(GraphQLString),
        },
    )
    field = GraphQLField(GraphQLNonNull(person_type))
    schema = convert_field_output_to_output_schema(field)
    assert schema.type == "object"
    assert schema.properties is not None
    assert "id" in schema.properties
    assert schema.properties["id"].type == "string"
    assert "name" in schema.properties
    assert schema.properties["name"].type == ["string", "null"]


def test_format_graphql_type_string():
    """Verify format_graphql_type_string outputs correct GraphQL syntax."""
    assert format_graphql_type_string(GraphQLString) == "String"
    assert format_graphql_type_string(GraphQLNonNull(GraphQLString)) == "String!"
    assert format_graphql_type_string(GraphQLList(GraphQLInt)) == "[Int]"
    assert format_graphql_type_string(GraphQLNonNull(GraphQLList(GraphQLNonNull(GraphQLID)))) == "[ID!]!"


def test_generate_default_selection_set_scalar_is_empty():
    """Scalars and enums do not require a selection set."""
    assert generate_default_selection_set(GraphQLString) == ""
    assert generate_default_selection_set(GraphQLInt) == ""
    assert generate_default_selection_set(GraphQLNonNull(GraphQLString)) == ""


def test_generate_default_selection_set_object_includes_scalars_and_nested():
    """Objects generate selection set with scalars and direct sub-relations."""
    Address = GraphQLObjectType(
        "Address",
        {
            "street": GraphQLField(GraphQLString),
            "city": GraphQLField(GraphQLString),
        },
    )
    Customer = GraphQLObjectType(
        "Customer",
        {
            "id": GraphQLField(GraphQLNonNull(GraphQLID)),
            "name": GraphQLField(GraphQLString),
            "address": GraphQLField(Address),
        },
    )

    selection = generate_default_selection_set(Customer, max_depth=2)
    assert "id" in selection
    assert "name" in selection
    assert "address { street city }" in selection


def test_generate_default_selection_set_union():
    """Unions generate inline fragments with __typename."""
    Dog = GraphQLObjectType("Dog", {"name": GraphQLField(GraphQLString), "bark": GraphQLField(GraphQLString)})
    Cat = GraphQLObjectType("Cat", {"name": GraphQLField(GraphQLString), "meow": GraphQLField(GraphQLString)})
    Pet = GraphQLUnionType("Pet", types=[Dog, Cat])

    selection = generate_default_selection_set(Pet, max_depth=2)
    assert "__typename" in selection
    assert "... on Dog { name bark }" in selection
    assert "... on Cat { name meow }" in selection


def test_generate_default_selection_set_cycle_protection():
    """Circular references stop at max depth without crashing and assert complete bounded string."""
    User = GraphQLObjectType(
        "User",
        lambda: {
            "id": GraphQLField(GraphQLNonNull(GraphQLID)),
            "bestFriend": GraphQLField(User),
        },
    )
    selection = generate_default_selection_set(User, max_depth=2)
    assert selection == "{ id bestFriend { id } }"


def test_generate_default_selection_set_skips_required_argument_fields():
    """Fields requiring arguments without defaults must not be auto-selected."""
    Item = GraphQLObjectType(
        "Item",
        {
            "id": GraphQLField(GraphQLNonNull(GraphQLID)),
            "name": GraphQLField(GraphQLString),
            "parameterizedField": GraphQLField(
                GraphQLString,
                args={"requiredArg": GraphQLArgument(GraphQLNonNull(GraphQLString))},
            ),
        },
    )
    selection = generate_default_selection_set(Item)
    assert "id" in selection
    assert "name" in selection
    assert "parameterizedField" not in selection


# =========================================================================
# Regression tests for Review Findings (Cubic Issues 1-12)
# =========================================================================

def test_defaulted_non_null_arguments_and_input_fields_not_required():
    """Finding 10: Non-null arguments and input fields with default values must not be required."""
    field = GraphQLField(
        GraphQLString,
        args={
            "requiredArg": GraphQLArgument(GraphQLNonNull(GraphQLString)),
            "defaultedArg": GraphQLArgument(GraphQLNonNull(GraphQLString), default_value="default_val"),
            "optionalArg": GraphQLArgument(GraphQLInt),
        },
    )
    schema = convert_field_args_to_input_schema(field)
    assert schema.required == ["requiredArg"]
    assert "defaultedArg" not in (schema.required or [])
    assert schema.properties["defaultedArg"].type == "string"
    assert schema.properties["defaultedArg"].default == "default_val"

    # Input object fields
    inp = GraphQLInputObjectType(
        "ConfigInput",
        {
            "mandatory": GraphQLInputField(GraphQLNonNull(GraphQLString)),
            "withDefault": GraphQLInputField(GraphQLNonNull(GraphQLInt), default_value=5),
            "optional": GraphQLInputField(GraphQLString),
        },
    )
    inp_schema = convert_graphql_type_to_json_schema(inp)
    assert inp_schema.required == ["mandatory"]
    assert "withDefault" not in (inp_schema.required or [])
    assert inp_schema.properties["withDefault"].default == 5


def test_json_scalar_unconstrained_types():
    """Finding 8: JSON scalar supports unconstrained types, JSONObject supports object."""
    json_scalar = GraphQLScalarType("JSON")
    schema_json = convert_graphql_type_to_json_schema(json_scalar)
    assert schema_json.type == ["object", "array", "string", "number", "boolean", "null"]

    json_obj_scalar = GraphQLScalarType("JSONObject")
    schema_obj = convert_graphql_type_to_json_schema(json_obj_scalar)
    assert schema_obj.type == ["object", "null"]

    # Non-null JSON and JSONObject
    nn_json = convert_graphql_type_to_json_schema(GraphQLNonNull(json_scalar))
    assert nn_json.type == ["object", "array", "string", "number", "boolean"]

    nn_obj = convert_graphql_type_to_json_schema(GraphQLNonNull(json_obj_scalar))
    assert nn_obj.type == "object"


def test_union_output_schema_one_of():
    """Finding 9: Union return schemas are represented using member-specific oneOf schemas with __typename const discriminator."""
    Dog = GraphQLObjectType("Dog", {"name": GraphQLField(GraphQLString), "bark": GraphQLField(GraphQLString)})
    Cat = GraphQLObjectType("Cat", {"name": GraphQLField(GraphQLString), "meow": GraphQLField(GraphQLString)})
    Pet = GraphQLUnionType("Pet", types=[Dog, Cat])

    # Nullable union
    schema_nullable = convert_graphql_type_to_json_schema(Pet)
    assert schema_nullable.oneOf is not None
    assert len(schema_nullable.oneOf) == 3  # Dog, Cat, null
    assert any(s.type == "null" for s in schema_nullable.oneOf)

    # Verify __typename discriminator prevents overlap between Dog and Cat
    dog_schema = next(s for s in schema_nullable.oneOf if s.properties and "__typename" in s.properties and s.properties["__typename"].const == "Dog")
    cat_schema = next(s for s in schema_nullable.oneOf if s.properties and "__typename" in s.properties and s.properties["__typename"].const == "Cat")
    assert "__typename" in dog_schema.required
    assert "__typename" in cat_schema.required
    assert dog_schema.properties["__typename"].const == "Dog"
    assert cat_schema.properties["__typename"].const == "Cat"

    # Non-null union
    schema_nn = convert_graphql_type_to_json_schema(GraphQLNonNull(Pet))
    assert schema_nn.oneOf is not None
    assert len(schema_nn.oneOf) == 2  # Dog, Cat
    assert not any(s.type == "null" for s in schema_nn.oneOf)


def test_nested_union_in_object_selection_set():
    """Finding 4: Support union-valued fields recursively inside object-returning fields."""
    Dog = GraphQLObjectType("Dog", {"name": GraphQLField(GraphQLString), "bark": GraphQLField(GraphQLString)})
    Cat = GraphQLObjectType("Cat", {"name": GraphQLField(GraphQLString), "meow": GraphQLField(GraphQLString)})
    Pet = GraphQLUnionType("Pet", types=[Dog, Cat])

    SearchResult = GraphQLObjectType(
        "SearchResult",
        {
            "totalCount": GraphQLField(GraphQLInt),
            "pet": GraphQLField(Pet),
        },
    )

    selection = generate_default_selection_set(SearchResult, max_depth=3)
    assert "totalCount" in selection
    assert "pet { __typename ... on Dog { name bark } ... on Cat { name meow } }" in selection


def test_object_without_scalar_fields_fallback_typename():
    """Finding 3: Valid leaf or __typename fallback instead of selecting first field blindly."""
    Sub = GraphQLObjectType("Sub", {"id": GraphQLField(GraphQLString)})
    EmptyScalars = GraphQLObjectType(
        "EmptyScalars",
        {
            "subWithReqArg": GraphQLField(
                Sub,
                args={"mandatory": GraphQLArgument(GraphQLNonNull(GraphQLString))},
            ),
        },
    )
    selection = generate_default_selection_set(EmptyScalars, max_depth=2)
    assert selection == "{ __typename }"


def test_depth_limit_without_identifier_fallback_typename():
    """Finding 12: Depth limit on object without id/code/name returns { __typename }."""
    Coordinate = GraphQLObjectType(
        "Coordinate",
        {
            "lat": GraphQLField(GraphQLFloat),
            "lng": GraphQLField(GraphQLFloat),
        },
    )
    # At max_depth=0 (or recursing beyond depth limit without id/name/code)
    selection = generate_default_selection_set(Coordinate, max_depth=0)
    assert selection == "{ __typename }"


def test_selection_depth_validation_ge_1():
    """Finding 11: selection_depth accepts >= 1 and rejects 0 or negative values."""
    template_valid = GraphQLCallTemplate(
        name="test",
        url="https://example.com/graphql",
        selection_depth=1,
    )
    assert template_valid.selection_depth == 1

    with pytest.raises(ValidationError):
        GraphQLCallTemplate(
            name="test",
            url="https://example.com/graphql",
            selection_depth=0,
        )

    with pytest.raises(ValidationError):
        GraphQLCallTemplate(
            name="test",
            url="https://example.com/graphql",
            selection_depth=-3,
        )


@pytest.mark.asyncio
async def test_operation_type_root_precedence_on_collision():
    """Finding 2: Resolve field using configured operation_type root first before falling back."""
    protocol = GraphQLCommunicationProtocol()
    ItemType = GraphQLObjectType("Item", {"id": GraphQLField(GraphQLString)})
    schema = GraphQLSchema(
        query=GraphQLObjectType("Query", {"item": GraphQLField(ItemType)}),
        mutation=GraphQLObjectType(
            "Mutation",
            {
                "item": GraphQLField(ItemType),
                "createItem": GraphQLField(ItemType),
            },
        ),
    )

    # 1. Operation type 'query' on colliding 'item' field -> generates query
    template_q = GraphQLCallTemplate(
        name="test_api",
        url="https://example.com/graphql",
        operation_type="query",
    )
    mock_session_q = AsyncMock()
    mock_session_q.client.schema = schema
    mock_client_q = MagicMock()
    mock_client_q.__aenter__.return_value = mock_session_q

    with patch("utcp_gql.gql_communication_protocol.GqlClient", return_value=mock_client_q), \
         patch("utcp_gql.gql_communication_protocol.gql_query") as mock_gql:
        await protocol.call_tool(None, "item", {}, template_q)
        executed_doc = mock_gql.call_args[0][0]
        assert executed_doc.startswith("query")

    # 2. Operation type 'mutation' on colliding 'item' field -> generates mutation
    template_m = GraphQLCallTemplate(
        name="test_api",
        url="https://example.com/graphql",
        operation_type="mutation",
    )
    mock_session_m = AsyncMock()
    mock_session_m.client.schema = schema
    mock_client_m = MagicMock()
    mock_client_m.__aenter__.return_value = mock_session_m

    with patch("utcp_gql.gql_communication_protocol.GqlClient", return_value=mock_client_m), \
         patch("utcp_gql.gql_communication_protocol.gql_query") as mock_gql:
        await protocol.call_tool(None, "item", {}, template_m)
        executed_doc = mock_gql.call_args[0][0]
        assert executed_doc.startswith("mutation")

    # 3. Operation type 'query', but field 'createItem' only exists on mutation -> falls back to mutation
    mock_session_fb = AsyncMock()
    mock_session_fb.client.schema = schema
    mock_client_fb = MagicMock()
    mock_client_fb.__aenter__.return_value = mock_session_fb

    with patch("utcp_gql.gql_communication_protocol.GqlClient", return_value=mock_client_fb), \
         patch("utcp_gql.gql_communication_protocol.gql_query") as mock_gql:
        await protocol.call_tool(None, "createItem", {}, template_q)
        executed_doc = mock_gql.call_args[0][0]
        assert executed_doc.startswith("mutation")


@pytest.mark.asyncio
async def test_session_execute_no_duplicate_mutation_on_type_error():
    """Finding 1: Compatibility fallback must not catch TypeError from session.execute and retry."""
    protocol = GraphQLCommunicationProtocol()
    template = GraphQLCallTemplate(
        name="test_api",
        url="https://example.com/graphql",
        operation_type="mutation",
    )
    ItemType = GraphQLObjectType("Item", {"id": GraphQLField(GraphQLString)})
    schema = GraphQLSchema(
        mutation=GraphQLObjectType("Mutation", {"createItem": GraphQLField(ItemType)})
    )
    mock_session = AsyncMock()
    mock_session.client.schema = schema
    mock_session.execute.side_effect = TypeError("Post-request serialization error")

    mock_client = MagicMock()
    mock_client.__aenter__.return_value = mock_session

    with patch("utcp_gql.gql_communication_protocol.GqlClient", return_value=mock_client):
        with pytest.raises(TypeError, match="Post-request serialization error"):
            await protocol.call_tool(None, "createItem", {}, template)

    # Must be executed exactly once, NEVER retried
    assert mock_session.execute.call_count == 1


