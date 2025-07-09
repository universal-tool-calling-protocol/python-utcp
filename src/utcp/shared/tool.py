from typing import Dict, Any, Optional, List, get_type_hints
from pydantic import BaseModel, Field, TypeAdapter
from utcp.shared.provider import ProviderUnion

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
    provider: ProviderUnion

class ToolContext:
    tools: List[Tool] = []

    @staticmethod
    def add_tool(tool: Tool):
        """Add a tool to the UTCP server."""

        print(f"Adding tool: {tool.name} with provider: {tool.provider.name if tool.provider else 'None'}")
        ToolContext.tools.append(tool)

    @staticmethod
    def get_tools() -> List[Tool]:
        """Get the list of tools available in the UTCP server."""
        return ToolContext.tools

def utcp_tool(
    provider: ProviderUnion,
    name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = ["utcp"],
    inputs: Optional[ToolInputOutputSchema] = None,
    outputs: Optional[ToolInputOutputSchema] = None,
):
    def decorator(func):
        if provider.name is None:
            _provider_name = f"{func.__name__}_provider"
            provider.name = _provider_name
        else:
            _provider_name = provider.name

        func_name = func.__name__
        func_description = description or func.__doc__ or ""
        
        if not inputs:
            # Extract input schema
            input_tool_schema = TypeAdapter(func).json_schema()
            input_tool_schema["title"] = func_name
            input_tool_schema["description"] = func_description
        
        if not outputs:
            # Extract output schema
            hints = get_type_hints(func)
            return_type = hints.pop("return", None)
            if return_type is not None:
                output_schema = TypeAdapter(return_type).json_schema()
                output_tool_schema = ToolInputOutputSchema(
                    type=output_schema.get("type", "object") if output_schema.get("type") == "object" else "value",
                    properties=output_schema.get("properties", {}) if output_schema.get("type") == "object" else {},
                    required=output_schema.get("required", []) if output_schema.get("type") == "object" else [],
                    title=func_name,
                    description=func_description
                )
            else:
                output_tool_schema = ToolInputOutputSchema(
                    type="null",
                    properties={},
                    required=[],
                    title=func_name,
                    description=func_description
                )
        
        # Create the complete tool definition
        def get_tool_definition():
            return Tool(
                name=name or func_name,
                description=description or func_description,
                tags=tags,
                inputs=inputs or input_tool_schema,
                outputs=outputs or output_tool_schema,
                provider=provider
            )
        
        # Attach methods to function
        func.input = lambda: input_tool_schema
        func.output = lambda: output_tool_schema
        func.tool_definition = get_tool_definition

        # Add the tool to the UTCP manual context
        ToolContext.add_tool(get_tool_definition())
        
        return func
    
    return decorator
