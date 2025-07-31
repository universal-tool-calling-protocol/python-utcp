import inspect
from typing import Dict, Any, Optional, List, Set, Tuple, get_type_hints, get_origin, get_args, Union
from pydantic import BaseModel, Field
from utcp.shared.provider import ProviderUnion


class ToolInputOutputSchema(BaseModel):
    type: str = Field(default="object")
    properties: Dict[str, Any] = Field(default_factory=dict)
    required: Optional[List[str]] = None
    description: Optional[str] = None
    title: Optional[str] = None
    items: Optional[Dict[str, Any]] = None  # For array types
    enum: Optional[List[Any]] = None  # For enum types
    minimum: Optional[float] = None  # For number types
    maximum: Optional[float] = None  # For number types
    format: Optional[str] = None  # For string formats

class Tool(BaseModel):
    name: str
    description: str = ""
    inputs: ToolInputOutputSchema = Field(default_factory=ToolInputOutputSchema)
    outputs: ToolInputOutputSchema = Field(default_factory=ToolInputOutputSchema)
    tags: List[str] = []
    average_response_size: Optional[int] = None
    tool_provider: ProviderUnion

class ToolContext:
    tools: List[Tool] = []

    @staticmethod
    def add_tool(tool: Tool):
        """Add a tool to the UTCP server."""

        print(f"Adding tool: {tool.name} with provider: {tool.tool_provider.name if tool.tool_provider else 'None'}")
        ToolContext.tools.append(tool)

    @staticmethod
    def get_tools() -> List[Tool]:
        """Get the list of tools available in the UTCP server."""
        return ToolContext.tools

########## UTCP Tool Decorator ##########
def python_type_to_json_type(py_type):
    origin = get_origin(py_type)
    args = get_args(py_type)

    if origin is Union:
        # Handle Optional[X] = Union[X, NoneType]
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            return python_type_to_json_type(non_none_args[0])  # Treat as Optional
        else:
            return "object"  # Generic union

    if origin is list or origin is List:
        return "array"
    if origin is dict or origin is Dict:
        return "object"
    if origin is tuple or origin is Tuple:
        return "array"
    if origin is set or origin is Set:
        return "array"

    # Handle concrete base types
    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        bytes: "string",
        type(None): "null",
        Any: "object",
    }

    return mapping.get(py_type, "object")

def get_docstring_description_input(func) -> Dict[str, Optional[str]]:
    """
    Extracts descriptions for parameters from the function docstring.
    Returns a dict mapping param names to their descriptions.
    """
    doc = func.__doc__
    if not doc:
        return {}
    descriptions = {}
    for line in map(str.strip, doc.splitlines()):
        for param in inspect.signature(func).parameters:
            if param == "self":
                continue
            if line.startswith(param):
                descriptions[param] = line.split(param, 1)[1].strip()
    return descriptions

def get_docstring_description_output(func) -> Dict[str, Optional[str]]:
    """
    Extracts the return value description from the function docstring.
    Returns a dict with key 'return' and its description.
    """
    doc = func.__doc__
    if not doc:
        return {}
    for i, line in enumerate(map(str.strip, doc.splitlines())):
        if line.lower().startswith("returns:") or line.lower().startswith("return:"):
            desc = line.split(":", 1)[1].strip()
            if desc:
                return {"return": desc}
            # If description is on the next line
            if i + 1 < len(doc.splitlines()):
                return {"return": doc.splitlines()[i + 1].strip()}
    return {}

def get_param_description(cls, param_name=None):
    # Try to get description for a specific param if available
    if param_name:
        # Check if there's a class variable or annotation with description
        doc = getattr(cls, "__doc__", "") or ""
        for line in map(str.strip, doc.splitlines()):
            if line.startswith(param_name):
                return line.split(param_name, 1)[1].strip()
        # Check if param has a 'description' attribute (for pydantic/BaseModel fields)
        if hasattr(cls, "__fields__") and param_name in cls.__fields__:
            return getattr(cls.__fields__[param_name], "field_info", {}).get("description", "")
    # Fallback to class-level description
    return getattr(cls, "description", "") or (getattr(cls, "__doc__", "") or "")

def is_optional(t):
    origin = get_origin(t)
    args = get_args(t)
    return origin is Union and type(None) in args

def recurse_type(param_type):
    json_type = python_type_to_json_type(param_type)

    # Handle array/list types
    if json_type == "array":
        # Try to get the element type if available
        item_type = getattr(param_type, "__args__", [Any])[0]
        return {
            "type": "array",
            "items": recurse_type(item_type),
            "description": "An array of items"
        }

    # Handle object types
    if json_type == "object":
        if hasattr(param_type, "__annotations__") or is_optional(param_type):
            sub_properties = {}
            sub_required = []
            
            if is_optional(param_type):
                # If it's Optional, we treat it as an object with no required fields
                param_type = param_type.__args__[0] if param_type.__args__ else Any
            for key, value_type in getattr(param_type, "__annotations__", {}).items():
                key_desc = get_param_description(param_type, key)
                sub_properties[key] = recurse_type(value_type)
                sub_properties[key]["description"] = key_desc or f"Auto-generated description for {key}"
                if value_type is not None and value_type is not type(None) and value_type is not Optional and not is_optional(value_type):
                    sub_required.append(key)
            return {
                "type": "object",
                "properties": sub_properties,
                "required": sub_required,
                "description": get_param_description(param_type)
            }

        return {
            "type": "object",
            "properties": {},
            "description": "A generic dictionary object"
        }

    # Fallback for primitive types
    return {
        "type": json_type,
        "description": ""
    }

def type_to_json_schema(param_type, param_name=None, param_description=None):
    json_type = python_type_to_json_type(param_type)

    # Recurse for object and dict types
    if json_type == "object":
        val = recurse_type(param_type)
        val["description"] = get_param_description(param_type, param_name) or param_description.get(param_name, f"Auto-generated description for {param_name}")
    elif json_type == "array" and hasattr(param_type, "__args__"):
        # Handle list/array types with recursion for element type
        item_type = param_type.__args__[0] if param_type.__args__ else Any
        val = {
            "type": "array",
            "items": recurse_type(item_type),
            "description": param_description.get(param_name, f"Auto-generated description for {param_name}")
        }
    else:
        val = {
            "type": json_type,
            "description": param_description.get(param_name, f"Auto-generated description for {param_name}")
        }
    
    return val

def generate_input_schema(func, title, description):
    sig = inspect.signature(func)
    type_hints = get_type_hints(func)

    properties = {}
    required = []

    func_name = func.__name__
    func_description = description or func.__doc__ or ""
    param_description = get_docstring_description_input(func)

    for param_name, param in sig.parameters.items():
        if param_name == "self":  # skip methods' self
            continue

        param_type = type_hints.get(param_name, str)
        properties[param_name] = type_to_json_schema(param_type, param_name, param_description)

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    input_desc = "\n".join([f"{name}: {desc}" for name, desc in param_description.items() if desc])
    schema = ToolInputOutputSchema(
        type="object",
        properties=properties,
        required=required,
        description=input_desc or func_description,
        title=title or func_name
    )

    return schema

def generate_output_schema(func, title, description):
    type_hints = get_type_hints(func)
    func_name = func.__name__
    func_description = description or func.__doc__ or ""

    properties = {}
    required = []

    return_type = type_hints.get('return', None)
    output_desc = get_docstring_description_output(func).get('return', None)
    if return_type:
        properties["result"] = type_to_json_schema(return_type, "result", {"result": output_desc})
        if return_type is not None and return_type is not type(None) and return_type is not Optional and not is_optional(return_type):
            required.append("result")
    else:
        properties["result"] = {
            "type": "null",
            "description": f"No return value for {func_name}"
        }

    schema = ToolInputOutputSchema(
        type="object",
        properties=properties,
        required=required,
        description=output_desc or func_description,
        title=title or func_name
    )

    return schema


def utcp_tool(
    tool_provider: ProviderUnion,
    name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = ["utcp"],
    inputs: Optional[ToolInputOutputSchema] = None,
    outputs: Optional[ToolInputOutputSchema] = None,
):
    def decorator(func):
        if tool_provider.name is None:
            tool_provider.name = f"{func.__name__}_provider"

        func_name = name or func.__name__
        func_description = description or func.__doc__ or ""

        input_tool_schema = inputs or generate_input_schema(func, f"{func_name} Input", func_description)
        output_tool_schema = outputs or generate_output_schema(func, f"{func_name} Output", func_description)

        def get_tool_definition():
            return Tool(
                name=func_name,
                description=func_description,
                tags=tags,
                inputs=input_tool_schema,
                outputs=output_tool_schema,
                tool_provider=tool_provider
            )

        func.input = lambda: input_tool_schema
        func.output = lambda: output_tool_schema
        func.tool_definition = get_tool_definition

        ToolContext.add_tool(get_tool_definition())

        return func

    return decorator
