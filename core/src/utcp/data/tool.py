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

JsonType = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]

class JsonSchema(BaseModel):
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
        "populate_by_name": True,  # replaces allow_population_by_field_name
        "extra": "allow"
    }

JsonSchema.model_rebuild()  # replaces update_forward_refs()

class JsonSchemaSerializer(Serializer[JsonSchema]):
    def to_dict(self, obj: JsonSchema) -> dict:
        return obj.model_dump()
    
    def validate_dict(self, obj: dict) -> JsonSchema:
        try:
            return JsonSchema.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid JSONSchema: " + str(e))

class Tool(BaseModel):
    """Definition of a UTCP tool.

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
    tags: List[str] = []
    average_response_size: Optional[int] = None
    tool_call_template: CallTemplate

    @field_serializer("tool_call_template")
    def serialize_call_template(cls, v: CallTemplate):
        return CallTemplateSerializer().to_dict(v)

    @field_validator("tool_call_template")
    @classmethod
    def validate_call_template(cls, v: Union[CallTemplate, dict]):
        if isinstance(v, CallTemplate):
            return v
        return CallTemplateSerializer().validate_dict(v)

class ToolSerializer(Serializer[Tool]):
    def to_dict(self, obj: Tool) -> dict:
        return obj.model_dump()

    def validate_dict(self, obj: dict) -> Tool:
        try:
            return Tool.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid Tool: " + str(e))
