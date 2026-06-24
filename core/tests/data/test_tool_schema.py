"""Tests for the JsonSchema model, including the `examples` field."""

from utcp.data.tool import JsonSchema, JsonSchemaSerializer


def test_jsonschema_examples_field_is_typed():
    """`examples` is a declared field, not just an extra attribute."""
    assert "examples" in JsonSchema.model_fields

    schema = JsonSchema(type="string", examples=["user123", "user456"])
    assert schema.examples == ["user123", "user456"]


def test_jsonschema_examples_default_none():
    """`examples` defaults to None when absent."""
    schema = JsonSchema(type="string")
    assert schema.examples is None


def test_jsonschema_examples_roundtrip():
    """`examples` survives serialize -> validate roundtrip."""
    serializer = JsonSchemaSerializer()
    schema = JsonSchema(
        type="object",
        examples=[{"id": "user123", "name": "John Doe"}],
    )

    as_dict = serializer.to_dict(schema)
    assert as_dict["examples"] == [{"id": "user123", "name": "John Doe"}]

    restored = serializer.validate_dict(as_dict)
    assert restored.examples == schema.examples


def test_jsonschema_examples_allows_mixed_json_types():
    """`examples` accepts any JSON value (string, bool, number, object)."""
    schema = JsonSchema(examples=["a", True, 1, 1.5, None, {"k": "v"}, [1, 2]])
    assert schema.examples == ["a", True, 1, 1.5, None, {"k": "v"}, [1, 2]]
