"""Tool definitions and schema generation for UTCP.

This module provides the core tool definition models and utilities for
automatic schema generation from Python functions. It supports both
manual tool definitions and decorator-based automatic tool creation.

Key Components:
    - Tool: The main tool definition model
    - JSONSchema: JSON Schema for tool inputs and outputs
    - ToolContext: Global tool registry
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_serializer, field_validator
from utcp.data.call_template import CallTemplate, CallTemplateSerializer
from utcp.interfaces.serializer import Serializer
from typing import Union
from utcp.exceptions import UtcpSerializerValidationError
import traceback

JsonType = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]

class JsonSchema(BaseModel):
    """REQUIRED
    JSON Schema for tool inputs and outputs.

    Attributes:
        schema_: Optional schema identifier.
        id_: Optional schema identifier.
        title: Optional schema title.
        description: Optional schema description.
        type: Optional schema type.
        properties: Optional schema properties.
        items: Optional schema items.
        required: Optional schema required fields.
        enum: Optional schema enum values.
        const: Optional schema constant value.
        default: Optional schema default value.
        format: Optional schema format.
        additionalProperties: Optional schema additional properties.
    """
    schema_: Optional[str] = Field(None, alias="$schema")
    id_: Optional[str] = Field(None, alias="$id")
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[Union[str, List[str]]] = None
    properties: Optional[Dict[str, "JsonSchema"]] = None
    items: Optional[Union["JsonSchema", List["JsonSchema"]]] = None
    required: Optional[List[str]] = None
    enum: Optional[List[JsonType]] = None
    const: Optional[JsonType] = None
    default: Optional[JsonType] = None
    format: Optional[str] = None
    additionalProperties: Optional[Union[bool, "JsonSchema"]] = None
    pattern: Optional[str] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    minLength: Optional[int] = None
    maxLength: Optional[int] = None

    model_config = {
        "validate_by_name": True,
        "validate_by_alias": True,
        "serialize_by_alias": True,
        "extra": "allow"
    }

JsonSchema.model_rebuild()  # replaces update_forward_refs()

class JsonSchemaSerializer(Serializer[JsonSchema]):
    """REQUIRED
    Serializer for JSON Schema.

    Defines the contract for serializers that convert JSON Schema to and from
    dictionaries for storage or transmission. Serializers are responsible for:
    - Converting JSON Schema to dictionaries for storage or transmission
    - Converting dictionaries back to JSON Schema
    - Ensuring data consistency during serialization and deserialization
    """
    def to_dict(self, obj: JsonSchema) -> dict:
        """REQUIRED
        Convert a JsonSchema object to a dictionary.

        Args:
            obj: The JsonSchema object to convert.

        Returns:
            The dictionary converted from the JsonSchema object.
        """
        return obj.model_dump(by_alias=True)
    
    def validate_dict(self, obj: dict) -> JsonSchema:
        """REQUIRED
        Validate a dictionary and convert it to a JsonSchema object.

        Args:
            obj: The dictionary to validate and convert.

        Returns:
            The JsonSchema object converted from the dictionary.
        """
        try:
            return JsonSchema.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid JSONSchema: " + traceback.format_exc()) from e

class Tool(BaseModel):
    """REQUIRED
    Definition of a UTCP tool.

    Represents a callable tool with its metadata, input/output schemas,
    and provider configuration. Tools are the fundamental units of
    functionality in the UTCP ecosystem.

    Attributes:
        name: Unique identifier for the tool, typically in format "provider.tool_name".
        description: Human-readable description of what the tool does.
        inputs: JSON Schema defining the tool's input parameters.
        outputs: JSON Schema defining the tool's return value structure.
        tags: List of tags for categorization and search.
        average_response_size: Optional hint about typical response size in bytes.
        tool_call_template: CallTemplate configuration for accessing this tool.
    """
    
    name: str
    description: str = ""
    inputs: JsonSchema = Field(default_factory=JsonSchema)
    outputs: JsonSchema = Field(default_factory=JsonSchema)
    tags: List[str] = Field(default_factory=list)
    average_response_size: Optional[int] = None
    tool_call_template: CallTemplate

    @field_serializer("tool_call_template")
    def serialize_call_template(self, call_template: CallTemplate):
        return CallTemplateSerializer().to_dict(call_template)

    @field_validator("tool_call_template", mode="before")
    @classmethod
    def validate_call_template(cls, v: Union[CallTemplate, dict]):
        if isinstance(v, CallTemplate):
            return v
        return CallTemplateSerializer().validate_dict(v)

class ToolSerializer(Serializer[Tool]):
    """REQUIRED
    Serializer for tools.

    Defines the contract for serializers that convert tools to and from
    dictionaries for storage or transmission. Serializers are responsible for:
    - Converting tools to dictionaries for storage or transmission
    - Converting dictionaries back to tools
    - Ensuring data consistency during serialization and deserialization
    """
    def to_dict(self, obj: Tool) -> dict:
        """REQUIRED
        Convert a Tool object to a dictionary.

        Args:
            obj: The Tool object to convert.

        Returns:
            The dictionary converted from the Tool object.
        """
        return obj.model_dump(by_alias=True)

    def validate_dict(self, obj: dict) -> Tool:
        """REQUIRED
        Validate a dictionary and convert it to a Tool object.

        Args:
            obj: The dictionary to validate and convert.

        Returns:
            The Tool object converted from the dictionary.
        """
        try:
            return Tool.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid Tool: " + traceback.format_exc()) from e
