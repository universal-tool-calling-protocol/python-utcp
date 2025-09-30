import inspect
from typing import Dict, Any, Optional, List, Set, Tuple, get_type_hints, get_origin, get_args, Union
from pydantic import BaseModel
from utcp.data.tool import Tool, JsonSchema
from utcp.data.call_template import CallTemplate

class ToolContext:
    """Global registry for UTCP tools.

    Maintains a centralized collection of all registered tools in the current
    process. Used by the @utcp_tool decorator to automatically register tools
    and by servers to discover available tools.

    Note:
        This is a class-level registry using static methods. All tools
        registered here are globally available within the process.
    """
    
    tools: List[Tool] = []

    @staticmethod
    def add_tool(tool: Tool) -> None:
        """Add a tool to the global tool registry.

        Args:
            tool: The tool definition to register.

        Note:
            Prints registration information for debugging purposes.
        """
        print(f"Adding tool: {tool.name} with call template: {tool.tool_call_template.name if tool.tool_call_template else 'None'}")
        ToolContext.tools.append(tool)

    @staticmethod
    def get_tools() -> List[Tool]:
        """Get all tools from the global registry.

        Returns:
            List of all registered Tool objects.
        """
        return ToolContext.tools

def python_type_to_json_type(py_type) -> str:
    """Convert Python type annotations to JSON Schema type strings.

    Maps Python type hints to their corresponding JSON Schema type names.
    Handles generic types, unions, and optional types.

    Args:
        py_type: Python type annotation to convert.

    Returns:
        JSON Schema type string (e.g., "string", "number", "array", "object").

    Examples:
        >>> python_type_to_json_type(str)
        "string"
        >>> python_type_to_json_type(List[int])
        "array"
        >>> python_type_to_json_type(Optional[str])
        "string"
    """
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
    """Extract parameter descriptions from function docstring.

    Parses the function's docstring to extract descriptions for each parameter.
    Looks for lines that start with parameter names followed by descriptions.

    Args:
        func: The function to extract parameter descriptions from.

    Returns:
        Dictionary mapping parameter names to their descriptions.
        Parameters without descriptions are omitted.

    Example:
        For a function with docstring containing "param1: Description of param1",
        returns {"param1": "Description of param1"}.
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
    """Extract return value description from function docstring.

    Parses the function's docstring to find the return value description.
    Looks for lines starting with "Returns:" or "Return:".

    Args:
        func: The function to extract return description from.

    Returns:
        Dictionary with "return" key mapped to the description,
        or empty dict if no return description is found.

    Example:
        For a docstring with "Returns: The computed result",
        returns {"return": "The computed result"}.
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

def get_param_description(cls, param_name: Optional[str] = None) -> str:
    """Extract parameter description from class docstring or field metadata.

    Attempts to find description for a parameter from various sources:
    1. Class docstring lines starting with parameter name
    2. Pydantic field descriptions
    3. Class-level description or docstring as fallback

    Args:
        cls: The class to extract description from.
        param_name: Optional specific parameter name to get description for.

    Returns:
        Description string for the parameter or class.
    """
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

def is_optional(t) -> bool:
    """Check if a type annotation represents an optional type.

    Determines if a type is Optional[T] (equivalent to Union[T, None]).

    Args:
        t: Type annotation to check.

    Returns:
        True if the type is optional (Union with None), False otherwise.

    Examples:
        >>> is_optional(Optional[str])
        True
        >>> is_optional(str)
        False
        >>> is_optional(Union[str, None])
        True
    """
    origin = get_origin(t)
    args = get_args(t)
    return origin is Union and type(None) in args

def recurse_type(param_type) -> Dict[str, Any]:
    """Recursively convert Python type to JSON Schema object.

    Creates a complete JSON Schema representation of a Python type,
    including nested objects, arrays, and their properties.

    Args:
        param_type: Python type annotation to convert.

    Returns:
        Dictionary representing the JSON Schema for the type.
        Includes type, properties, items, required fields, and descriptions.

    Examples:
        >>> recurse_type(List[str])
        {"type": "array", "items": {"type": "string"}, "description": "An array of items"}
    """
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

def type_to_json_schema(param_type, param_name: Optional[str] = None, param_description: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Convert Python type to JSON Schema with description handling.

    Creates a JSON Schema representation of a Python type with appropriate
    descriptions from parameter documentation or auto-generated fallbacks.

    Args:
        param_type: Python type annotation to convert.
        param_name: Optional parameter name for description lookup.
        param_description: Optional dictionary of parameter descriptions.

    Returns:
        JSON Schema dictionary with type, description, and structure information.
    """
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

def generate_input_schema(func, title: Optional[str], description: Optional[str]) -> JsonSchema:
    """Generate input schema for a function's parameters.

    Analyzes a function's signature and type hints to create a JSON Schema
    that describes the function's input parameters. Extracts parameter
    descriptions from the function's docstring.

    Args:
        func: Function to generate input schema for.
        title: Optional title for the schema.
        description: Optional description for the schema.

    Returns:
        JSONSchema object describing the function's input parameters.
        Includes parameter types, required fields, and descriptions.
    """
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
    schema = JsonSchema(
        type="object",
        properties=properties,
        required=required,
        description=input_desc or func_description,
        title=title or func_name
    )

    return schema

def generate_output_schema(func, title: Optional[str], description: Optional[str]) -> JsonSchema:
    """Generate output schema for a function's return value.

    Analyzes a function's return type annotation to create a JSON Schema
    that describes the function's output. Extracts return value description
    from the function's docstring.

    Args:
        func: Function to generate output schema for.
        title: Optional title for the schema.
        description: Optional description for the schema.

    Returns:
        JSONSchema object describing the function's return value.
        Contains "result" property with the return type and description.
    """
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

    schema = JsonSchema(
        type="object",
        properties=properties,
        required=required,
        description=output_desc or func_description,
        title=title or func_name
    )

    return schema


def utcp_tool(
    tool_call_template: CallTemplate,
    name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = ["utcp"],
    inputs: Optional[JsonSchema] = None,
    outputs: Optional[JsonSchema] = None,
):
    """Decorator to convert Python functions into UTCP tools.

    Automatically generates tool definitions with input/output schemas from
    function signatures and type hints. Registers the tool in the global
    ToolContext for discovery.

    Args:
        tool_call_template: Call template for accessing this tool.
        name: Optional custom name for the tool. Defaults to function name.
        description: Optional description. Defaults to function docstring.
        tags: Optional list of tags for categorization. Defaults to ["utcp"].
        inputs: Optional manual input schema. Auto-generated if not provided.
        outputs: Optional manual output schema. Auto-generated if not provided.

    Returns:
        Decorator function that transforms the target function into a UTCP tool.

    Note:
        The decorated function gains additional attributes:
        - input(): Returns the input schema
        - output(): Returns the output schema
        - tool_definition(): Returns the complete Tool object
    """
    def decorator(func):
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
                tool_call_template=tool_call_template
            )

        func.input = lambda: input_tool_schema
        func.output = lambda: output_tool_schema
        func.tool_definition = get_tool_definition

        ToolContext.add_tool(get_tool_definition())

        return func

    return decorator
