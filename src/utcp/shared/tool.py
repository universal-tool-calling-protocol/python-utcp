import inspect
from typing import Dict, Any, Optional, List, Literal, Union, get_type_hints
from pydantic import BaseModel, Field, TypeAdapter
from utcp.shared.provider import (
    HttpProvider,
    CliProvider,
    WebSocketProvider,
    GRPCProvider,
    GraphQLProvider,
    TCPProvider,
    UDPProvider,
    StreamableHttpProvider,
    SSEProvider,
    WebRTCProvider,
    MCPProvider,
    TextProvider,
)

class ToolInputOutputSchema(BaseModel):
    type: str = Field(default="object")
    properties: Dict[str, Any] = Field(default_factory=dict)
    required: Optional[List[str]] = None
    description: Optional[str] = None
    title: Optional[str] = None

class Tool(BaseModel):
    name: str
    description: str = ""
    inputs: ToolInputOutputSchema = Field(default_factory=ToolInputOutputSchema)
    outputs: ToolInputOutputSchema = Field(default_factory=ToolInputOutputSchema)
    tags: List[str] = []
    average_response_size: Optional[int] = None
    provider: Optional[Union[
        HttpProvider,
        CliProvider,
        WebSocketProvider,
        GRPCProvider,
        GraphQLProvider,
        TCPProvider,
        UDPProvider,
        StreamableHttpProvider,
        SSEProvider,
        WebRTCProvider,
        MCPProvider,
        TextProvider,
    ]] = None

def utcp_tool(title: str, description: str = ""):
    """Decorator to create a UTCP tool with input and output schemas.
    
    Args:
        title (str): The title of the tool.
        description (str): A brief description of the tool.
    Returns:
        function: The decorated function with input and output schemas attached.
    """
    def decorator(func):
        # Extract input schema
        input_tool_schema = TypeAdapter(func).json_schema()
        input_tool_schema["title"] = title + " - Input"
        input_tool_schema["description"] = description + " - Input"

        # Extract output schema
        hints = get_type_hints(func)

        return_type = hints.pop("return", None)
        if return_type is not None:
            output_schema = TypeAdapter(return_type).json_schema()
            output_tool_schema = ToolInputOutputSchema(
                type=output_schema.get("type", "object") if output_schema.get("type") == "object" else "value",
                properties=output_schema.get("properties", {}) if output_schema.get("type") == "object" else {},
                required=output_schema.get("required", []) if output_schema.get("type") == "object" else [],
                title=title + " - Output",
                description=description + " - Output"
            )
        else:
            output_tool_schema = ToolInputOutputSchema(
                type="null",
                properties={},
                required=[],
                title=title + " - Output",
                description=description + " - Output"
            )

        func.input = lambda: input_tool_schema
        func.output = lambda: output_tool_schema
        return func
    
    return decorator
