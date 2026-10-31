"""GraphQL to UTCP JSON Schema converter and query generator.

This module provides conversion utilities that bridge GraphQL schemas and
UTCP tool definitions:
1. Translates GraphQL input arguments and types into standard UTCP JsonSchema objects.
2. Translates GraphQL output types into JSON Schema for tool return values.
3. Automatically generates valid GraphQL selection sets for object return types so
   auto-generated queries do not fail with missing selection set errors.
"""

from typing import Any, Dict, List, Optional, Set
from graphql import (
    GraphQLArgument,
    GraphQLField,
    GraphQLType,
    Undefined,
    is_enum_type,
    is_input_object_type,
    is_interface_type,
    is_list_type,
    is_non_null_type,
    is_object_type,
    is_scalar_type,
    is_union_type,
)
from utcp.data.tool import JsonSchema, JsonType


# Mapping of standard GraphQL scalar names to JSON Schema types
SCALAR_TYPE_MAP: Dict[str, Dict[str, Any]] = {
    "String": {"type": "string"},
    "Int": {"type": "integer"},
    "Float": {"type": "number"},
    "Boolean": {"type": "boolean"},
    "ID": {"type": "string", "description": "Unique identifier"},
    "JSON": {"type": "object"},
    "JSONObject": {"type": "object"},
    "DateTime": {"type": "string", "format": "date-time"},
    "Date": {"type": "string", "format": "date"},
    "Time": {"type": "string", "format": "time"},
    "UUID": {"type": "string", "format": "uuid"},
}


def convert_graphql_type_to_json_schema(
    gql_type: GraphQLType,
    description: Optional[str] = None,
    default_value: Optional[JsonType] = None,
    visited: Optional[Set[str]] = None,
    depth: int = 0,
    max_depth: int = 3,
) -> JsonSchema:
    """Convert any GraphQL type into an equivalent UTCP JsonSchema.

    Handles NonNull wrappers, Lists, Scalars, Enums, InputObjects, and Objects,
    with cycle protection for recursive schemas.
    """
    if visited is None:
        visited = set()

    # Unwrap NonNull: the outer field/argument container tracks requirement
    if is_non_null_type(gql_type):
        return convert_graphql_type_to_json_schema(
            gql_type.of_type,
            description=description,
            default_value=default_value,
            visited=visited,
            depth=depth,
            max_depth=max_depth,
        )

    # Lists -> Array schema
    if is_list_type(gql_type):
        item_schema = convert_graphql_type_to_json_schema(
            gql_type.of_type,
            visited=visited,
            depth=depth + 1,
            max_depth=max_depth,
        )
        return JsonSchema(
            type="array",
            items=item_schema,
            description=description,
            default=default_value,
        )

    # Standard and custom scalars
    if is_scalar_type(gql_type):
        mapping = SCALAR_TYPE_MAP.get(gql_type.name, {"type": "string"})
        desc = description or mapping.get("description") or getattr(gql_type, "description", None)
        return JsonSchema(
            type=mapping.get("type", "string"),
            format=mapping.get("format"),
            description=desc,
            default=default_value,
        )

    # Enum types
    if is_enum_type(gql_type):
        enum_values = list(gql_type.values.keys())
        desc = description or getattr(gql_type, "description", None)
        return JsonSchema(
            type="string",
            enum=enum_values,
            description=desc,
            default=default_value,
        )

    # Input object types (used in arguments)
    if is_input_object_type(gql_type):
        type_name = getattr(gql_type, "name", "")
        desc = description or getattr(gql_type, "description", None)

        if type_name in visited or depth >= max_depth:
            return JsonSchema(type="object", description=desc, default=default_value)

        visited_branch = visited | {type_name}
        properties: Dict[str, JsonSchema] = {}
        required: List[str] = []

        for field_name, input_field in gql_type.fields.items():
            field_t = input_field.type
            if is_non_null_type(field_t):
                required.append(field_name)

            def_val = (
                input_field.default_value
                if input_field.default_value is not None
                and input_field.default_value is not Undefined
                else None
            )

            properties[field_name] = convert_graphql_type_to_json_schema(
                field_t,
                description=input_field.description,
                default_value=def_val,
                visited=visited_branch,
                depth=depth + 1,
                max_depth=max_depth,
            )

        return JsonSchema(
            type="object",
            properties=properties if properties else None,
            required=required if required else None,
            description=desc,
            default=default_value,
        )

    # Object types & Interface types (used in outputs)
    if is_object_type(gql_type) or is_interface_type(gql_type):
        type_name = getattr(gql_type, "name", "")
        desc = description or getattr(gql_type, "description", None)

        if type_name in visited or depth >= max_depth:
            return JsonSchema(type="object", description=desc, default=default_value)

        visited_branch = visited | {type_name}
        properties = {}
        for field_name, out_field in gql_type.fields.items():
            properties[field_name] = convert_graphql_type_to_json_schema(
                out_field.type,
                description=out_field.description,
                visited=visited_branch,
                depth=depth + 1,
                max_depth=max_depth,
            )

        return JsonSchema(
            type="object",
            properties=properties if properties else None,
            description=desc,
            default=default_value,
        )

    # Union types
    if is_union_type(gql_type):
        desc = description or getattr(gql_type, "description", None)
        return JsonSchema(type="object", description=desc, default=default_value)

    return JsonSchema(type="object", description=description, default=default_value)


def convert_field_args_to_input_schema(field: GraphQLField) -> JsonSchema:
    """Convert a GraphQLField's arguments into a UTCP input JsonSchema.

    Populates `properties`, marks `GraphQLNonNull` arguments as `required`,
    and sets descriptions and default values.
    """
    if not field.args:
        return JsonSchema(type="object")

    properties: Dict[str, JsonSchema] = {}
    required: List[str] = []

    for arg_name, arg in field.args.items():
        arg_t = arg.type
        if is_non_null_type(arg_t):
            required.append(arg_name)

        def_val = (
            arg.default_value
            if arg.default_value is not None and arg.default_value is not Undefined
            else None
        )

        properties[arg_name] = convert_graphql_type_to_json_schema(
            arg_t,
            description=arg.description,
            default_value=def_val,
        )

    return JsonSchema(
        type="object",
        properties=properties if properties else None,
        required=required if required else None,
    )


def convert_field_output_to_output_schema(field: GraphQLField) -> JsonSchema:
    """Convert a GraphQLField's return type into a UTCP output JsonSchema."""
    return convert_graphql_type_to_json_schema(
        field.type,
        description=field.description,
    )


def format_graphql_type_string(gql_type: GraphQLType) -> str:
    """Return the GraphQL syntax string for a type (e.g. 'ID!', '[String]', 'CountryFilterInput')."""
    if is_non_null_type(gql_type):
        return f"{format_graphql_type_string(gql_type.of_type)}!"
    if is_list_type(gql_type):
        return f"[{format_graphql_type_string(gql_type.of_type)}]"
    if hasattr(gql_type, "name"):
        return gql_type.name
    return "String"


def generate_default_selection_set(
    gql_type: GraphQLType,
    max_depth: int = 2,
    current_depth: int = 0,
    visited: Optional[Set[str]] = None,
) -> str:
    """Generate a clean GraphQL selection set string for object types.

    Returns an empty string for scalar and enum return types.
    For Object types, includes scalar and enum fields, and recurses up to `max_depth`.
    """
    if visited is None:
        visited = set()

    # Unwrap NonNull and List
    actual_type = gql_type
    while is_non_null_type(actual_type) or is_list_type(actual_type):
        actual_type = actual_type.of_type

    if is_scalar_type(actual_type) or is_enum_type(actual_type):
        return ""

    if is_object_type(actual_type) or is_interface_type(actual_type):
        type_name = getattr(actual_type, "name", "")
        if type_name in visited or current_depth >= max_depth:
            # Fall back to an identifier or name if present
            for id_field in ("id", "code", "name"):
                if id_field in actual_type.fields:
                    return f"{{ {id_field} }}"
            return ""

        visited_branch = visited | {type_name}
        selections: List[str] = []

        for field_name, field in actual_type.fields.items():
            # Skip fields with mandatory arguments that have no default value
            if field.args and any(
                is_non_null_type(a.type) and (a.default_value is None or a.default_value is Undefined)
                for a in field.args.values()
            ):
                continue

            f_type = field.type
            while is_non_null_type(f_type) or is_list_type(f_type):
                f_type = f_type.of_type

            if is_scalar_type(f_type) or is_enum_type(f_type):
                selections.append(field_name)
            elif (is_object_type(f_type) or is_interface_type(f_type)) and current_depth + 1 < max_depth:
                sub_sel = generate_default_selection_set(
                    f_type,
                    max_depth=max_depth,
                    current_depth=current_depth + 1,
                    visited=visited_branch,
                )
                if sub_sel:
                    selections.append(f"{field_name} {sub_sel}")

        if not selections:
            # If no scalars were found, pick the first available field
            for field_name in actual_type.fields.keys():
                selections.append(field_name)
                break

        return f"{{ {' '.join(selections)} }}" if selections else ""

    if is_union_type(actual_type):
        type_name = getattr(actual_type, "name", "")
        if type_name in visited or current_depth >= max_depth:
            return "{ __typename }"

        visited_branch = visited | {type_name}
        fragments: List[str] = ["__typename"]
        for member_type in actual_type.types:
            member_sel = generate_default_selection_set(
                member_type,
                max_depth=max_depth,
                current_depth=current_depth + 1,
                visited=visited_branch,
            )
            if member_sel:
                fragments.append(f"... on {member_type.name} {member_sel}")

        return f"{{ {' '.join(fragments)} }}"

    return ""
