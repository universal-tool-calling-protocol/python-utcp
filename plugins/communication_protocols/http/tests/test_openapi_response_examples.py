from copy import deepcopy

import pytest

from utcp_http.openapi_converter import OpenApiConverter


def swagger_spec(response, status="200"):
    return {
        "swagger": "2.0",
        "info": {"title": "Example API", "version": "1.0"},
        "host": "api.example.com",
        "schemes": ["https"],
        "paths": {
            "/items": {
                "get": {
                    "operationId": "getItems",
                    "responses": {status: response},
                }
            }
        },
    }


@pytest.mark.parametrize(
    "schema, example",
    [
        ({"type": "object"}, {"value": "literal", "summary": "payload"}),
        ({"type": "object"}, {"$ref": "#/definitions/Result"}),
        ({"type": "object"}, {"externalValue": "https://example.com/sample"}),
        ({"type": "array", "items": {"type": "integer"}}, [1, 2]),
        ({"type": "array", "items": {"type": "integer"}}, []),
        ({"type": "boolean"}, False),
        ({"type": "integer"}, 0),
        ({"type": "string"}, ""),
        ({"type": "object", "x-nullable": True}, None),
    ],
)
def test_swagger_response_examples_preserve_raw_values(schema, example):
    spec = swagger_spec({
        "description": "OK",
        "schema": schema,
        "examples": {"application/json": example},
    })
    spec["definitions"] = {"Result": {"type": "string", "example": "resolved"}}
    original = deepcopy(spec)

    tool = OpenApiConverter(spec).convert().tools[0]

    assert tool.outputs.examples == [example]
    assert tool.outputs.model_dump(by_alias=True)["examples"] == [example]
    assert spec == original


@pytest.mark.parametrize("status", ["200", "201", "default"])
def test_swagger_response_examples_merge_media_types_and_schema(status):
    spec = swagger_spec({
        "description": "OK",
        "schema": {"$ref": "#/definitions/Result"},
        "examples": {
            "application/json": {"id": 1, "name": "widget"},
            "application/vnd.example+json": {"name": "widget", "id": 1},
            "application/xml": "<item>widget</item>",
        },
    }, status=status)
    spec["definitions"] = {
        "Result": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
            "example": {"id": 2, "name": "other"},
        }
    }

    tool = OpenApiConverter(spec).convert().tools[0]

    assert tool.outputs.properties["id"].type == "integer"
    assert tool.outputs.examples == [
        {"id": 1, "name": "widget"},
        "<item>widget</item>",
        {"id": 2, "name": "other"},
    ]


def test_swagger_response_examples_deduplicate_without_collapsing_json_types():
    spec = swagger_spec({
        "description": "OK",
        "schema": {"description": "A JSON value", "example": True},
        "examples": {
            "application/json": True,
            "application/vnd.example+json": 1,
            "application/vnd.other+json": True,
        },
    })

    examples = OpenApiConverter(spec).convert().tools[0].outputs.examples

    assert examples == [True, 1]
    assert [type(value) for value in examples] == [bool, int]


@pytest.mark.parametrize("response_examples", [{}, None, ["not a MIME map"]])
def test_swagger_response_without_example_map_keeps_schema_example(response_examples):
    spec = swagger_spec({
        "description": "OK",
        "schema": {"type": "string", "example": "schema example"},
        "examples": response_examples,
    })

    assert OpenApiConverter(spec).convert().tools[0].outputs.examples == ["schema example"]
