"""Unit tests for the GraphQL to JSON Schema converter and selection set generator.

These tests run completely offline and mock GraphQL schemas using graphql-core.
"""

import pytest
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
    GraphQLString,
)

from utcp_gql.schema_converter import (
    convert_field_args_to_input_schema,
    convert_field_output_to_output_schema,
    convert_graphql_type_to_json_schema,
    format_graphql_type_string,
    generate_default_selection_set,
)


def test_convert_scalar_types():
    """Verify standard and custom scalars map to appropriate JSON Schema types."""
    str_schema = convert_graphql_type_to_json_schema(GraphQLString, description="A string")
    assert str_schema.type == "string"
    assert str_schema.description == "A string"

    int_schema = convert_graphql_type_to_json_schema(GraphQLInt, default_value=42)
    assert int_schema.type == "integer"
    assert int_schema.default == 42

    float_schema = convert_graphql_type_to_json_schema(GraphQLFloat)
    assert float_schema.type == "number"

    id_schema = convert_graphql_type_to_json_schema(GraphQLID)
    assert id_schema.type == "string"
    assert "identifier" in (id_schema.description or "").lower()

    # Custom scalar
    date_scalar = GraphQLScalarType(name="DateTime", description="ISO timestamp")
    dt_schema = convert_graphql_type_to_json_schema(date_scalar)
    assert dt_schema.type == "string"
    assert dt_schema.format == "date-time"


def test_convert_non_null_type():
    """Verify NonNull unwraps to the inner type."""
    non_null_str = GraphQLNonNull(GraphQLString)
    schema = convert_graphql_type_to_json_schema(non_null_str)
    assert schema.type == "string"


def test_convert_list_type():
    """Verify GraphQLList maps to an array schema with items."""
    list_of_ints = GraphQLList(GraphQLInt)
    schema = convert_graphql_type_to_json_schema(list_of_ints)
    assert schema.type == "array"
    assert schema.items is not None
    assert schema.items.type == "integer"


def test_convert_enum_type():
    """Verify GraphQLEnumType maps to a string with enum values."""
    role_enum = GraphQLEnumType(
        "Role",
        {
            "ADMIN": GraphQLEnumValue(description="Administrator"),
            "USER": GraphQLEnumValue(description="Regular user"),
            "GUEST": GraphQLEnumValue(description="Guest"),
        },
    )
    schema = convert_graphql_type_to_json_schema(role_enum)
    assert schema.type == "string"
    assert schema.enum == ["ADMIN", "USER", "GUEST"]


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
    assert schema.type == "object"
    assert schema.properties is not None
    assert "username" in schema.properties
    assert schema.properties["username"].type == "string"
    assert "age" in schema.properties
    assert schema.properties["age"].type == "integer"
    assert schema.properties["age"].default == 18
    assert "tags" in schema.properties
    assert schema.properties["tags"].type == "array"
    assert schema.required == ["username"]


def test_convert_input_object_cycle_protection():
    """Verify recursive input objects do not trigger infinite recursion."""
    node_input = GraphQLInputObjectType(
        "NodeInput",
        lambda: {
            "name": GraphQLInputField(GraphQLString),
            "parent": GraphQLInputField(node_input),
        },
    )
    schema = convert_graphql_type_to_json_schema(node_input, max_depth=2)
    assert schema.type == "object"
    assert schema.properties is not None
    assert "name" in schema.properties
    assert "parent" in schema.properties
    assert schema.properties["parent"].type == "object"


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
    assert schema.properties["limit"].type == "integer"
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
    assert "name" in schema.properties


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
    from graphql import GraphQLUnionType

    Dog = GraphQLObjectType("Dog", {"name": GraphQLField(GraphQLString), "bark": GraphQLField(GraphQLString)})
    Cat = GraphQLObjectType("Cat", {"name": GraphQLField(GraphQLString), "meow": GraphQLField(GraphQLString)})
    Pet = GraphQLUnionType("Pet", types=[Dog, Cat])

    selection = generate_default_selection_set(Pet, max_depth=2)
    assert "__typename" in selection
    assert "... on Dog { name bark }" in selection
    assert "... on Cat { name meow }" in selection


def test_generate_default_selection_set_cycle_protection():
    """Circular references stop at max depth without crashing."""
    User = GraphQLObjectType(
        "User",
        lambda: {
            "id": GraphQLField(GraphQLNonNull(GraphQLID)),
            "bestFriend": GraphQLField(User),
        },
    )
    selection = generate_default_selection_set(User, max_depth=2)
    assert "id" in selection
    assert "bestFriend" in selection


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

