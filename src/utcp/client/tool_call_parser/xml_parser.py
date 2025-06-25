"""
XML Tool Call Parser for UTCP.

This module provides an XML-based parsing strategy for tool calls, offering a standardized
format for tool invocations similar to what is used in systems like Cline.
"""

import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, Tuple, Optional, List
import json
from utcp.shared.tool import Tool

class XmlToolCallParser:
    """
    Parser for XML-formatted tool calls in UTCP.
    
    This class provides methods to:
    1. Generate example XML for a tool call based on its ToolDeclaration
    2. Parse XML strings to extract tool name and arguments
    """
    
    @staticmethod
    def generate_example_xml(tool_declaration: Tool) -> str:
        """
        Generate an example XML string for calling a tool based on its declaration.
        
        Args:
            tool_declaration: The ToolDeclaration object containing tool metadata
            
        Returns:
            An XML string showing how to call the tool
        """
        name = tool_declaration.name
        result = f"<{name}>\n"
        
        # Add parameters based on the input schema
        if tool_declaration.inputs and tool_declaration.inputs.properties:
            for param_name, param_props in tool_declaration.inputs.properties.items():
                param_type = param_props.get("type", "string")
                description = param_props.get("description", "")
                required = tool_declaration.inputs.required and param_name in tool_declaration.inputs.required
                
                # Format the parameter comment
                comment = f"<!-- {description}"
                if required:
                    comment += " (required)"
                comment += " -->"
                
                # Generate example value based on the parameter type
                example_value = XmlToolCallParser._generate_example_value(param_type, param_props)
                
                # Format the parameter line
                result += f"  {comment}\n"
                result += f"  <{param_name}>{example_value}</{param_name}>\n"
        
        result += f"</{name}>"
        return result
    
    @staticmethod
    def _generate_example_value(param_type: str, param_props: Dict[str, Any]) -> str:
        """
        Generate an example value for a parameter based on its type.
        
        Args:
            param_type: The JSON schema type of the parameter
            param_props: Additional properties from the JSON schema
            
        Returns:
            A string representation of an example value
        """
        if param_type == "string":
            if "enum" in param_props:
                return str(param_props["enum"][0])
            return "example_string"
        elif param_type == "integer":
            return "42"
        elif param_type == "number":
            return "3.14"
        elif param_type == "boolean":
            return "true"
        elif param_type == "array":
            items_type = param_props.get("items", {}).get("type", "string")
            return f"[\"{XmlToolCallParser._generate_example_value(items_type, param_props.get('items', {}))}\"]"
        elif param_type == "object":
            return "{\"key\": \"value\"}"
        return "value"

    @staticmethod
    def parse_xml(xml_str: str) -> Tuple[str, Dict[str, Any]]:
        """
        Parse an XML-formatted tool call string to extract the tool name and arguments.
        
        The parser is lenient and handles various formats including:
        - Standard XML with proper nesting
        - XML without proper closing tags
        - XML with malformed tags
        
        Args:
            xml_str: The XML string representing a tool call
            
        Returns:
            A tuple containing (tool_name, arguments_dict)
            
        Raises:
            ValueError: If the XML string cannot be parsed or is missing required elements
        """
        # Remove any XML declaration if present
        xml_str = re.sub(r'<\?xml[^>]*\?>', '', xml_str)
        
        # Try to determine the tool name from the first tag
        tool_name_match = re.search(r'<([a-zA-Z0-9_]+)[>\\s]', xml_str)
        if not tool_name_match:
            raise ValueError("Could not determine tool name from XML string")
        
        tool_name = tool_name_match.group(1)
        
        # Try multiple parsing strategies
        errors = []
        try:
            # First try standard XML parsing
            return XmlToolCallParser._parse_standard_xml(xml_str)
        except Exception as e:
            errors.append(f"Standard XML parsing failed: {str(e)}")
            try:
                # If standard parsing fails, try a more lenient approach
                return XmlToolCallParser._parse_lenient_xml(xml_str)
            except Exception as e2:
                errors.append(f"Lenient XML parsing failed: {str(e2)}")
                try:
                    # As a last resort, try to extract parameters with regex
                    return XmlToolCallParser._parse_regex_xml(xml_str)
                except Exception as e3:
                    errors.append(f"Regex XML parsing failed: {str(e3)}")
                    raise ValueError(f"Failed to parse XML after trying all methods: {'; '.join(errors)}")
    
    @staticmethod
    def _parse_standard_xml(xml_str: str) -> Tuple[str, Dict[str, Any]]:
        """Parse XML using standard ElementTree parsing."""
        try:
            # Wrap in a root element if there might be multiple tags at the top level
            wrapped_xml = f"<root>{xml_str}</root>"
            root = ET.fromstring(wrapped_xml)
            
            # The first child is our tool element
            tool_element = root[0]
            tool_name = tool_element.tag
            
            # Extract parameters
            params = {}
            for param_element in tool_element:
                # Try to parse JSON if it looks like JSON
                param_text = param_element.text or ""
                param_value = XmlToolCallParser._parse_parameter_value(param_text)
                params[param_element.tag] = param_value
                
            return tool_name, params
        except Exception as e:
            # If parsing fails with wrapper, try direct parsing
            root = ET.fromstring(xml_str)
            tool_name = root.tag
            
            # Extract parameters
            params = {}
            for param_element in root:
                param_text = param_element.text or ""
                param_value = XmlToolCallParser._parse_parameter_value(param_text)
                params[param_element.tag] = param_value
                
            return tool_name, params
    
    @staticmethod
    def _parse_lenient_xml(xml_str: str) -> Tuple[str, Dict[str, Any]]:
        """
        Parse XML in a more lenient way by fixing common issues first.
        """
        # Clean up the XML by fixing common issues
        # 1. Find the tool name (first tag)
        tool_name_match = re.search(r'<([a-zA-Z0-9_]+)[>\\s]', xml_str)
        if not tool_name_match:
            raise ValueError("Could not determine tool name from XML string")
        
        tool_name = tool_name_match.group(1)
        
        # 2. Extract parameters - two approaches for different formats
        # First pattern: Find parameters with proper closing tags
        params = {}
        proper_param_pattern = r'<([a-zA-Z0-9_]+)>(.*?)</\1>'
        
        for match in re.finditer(proper_param_pattern, xml_str, re.DOTALL):
            param_name = match.group(1)
            param_text = match.group(2).strip()
            
            # Skip if this is the tool name itself
            if param_name == tool_name:
                continue
                
            param_value = XmlToolCallParser._parse_parameter_value(param_text)
            params[param_name] = param_value
        
        # If we didn't find any parameters with proper closing tags,
        # try finding parameters with only opening tags
        if not params:
            # Extract lines that look like parameters
            lines = xml_str.split('\n')
            param_start_pattern = r'\s*<([a-zA-Z0-9_]+)>\s*(.*)'
            
            for i, line in enumerate(lines):
                match = re.match(param_start_pattern, line)
                if match:
                    param_name = match.group(1)
                    param_text = match.group(2).strip()
                    
                    # Skip if this is the tool name
                    if param_name == tool_name:
                        continue
                    
                    # If this line contains another opening tag, extract just the content before it
                    next_tag_match = re.search(r'<([a-zA-Z0-9_]+)>', param_text)
                    if next_tag_match:
                        tag_pos = next_tag_match.start()
                        param_text = param_text[:tag_pos].strip()
                    
                    param_value = XmlToolCallParser._parse_parameter_value(param_text)
                    params[param_name] = param_value
        
        return tool_name, params
    
    @staticmethod
    def _parse_regex_xml(xml_str: str) -> Tuple[str, Dict[str, Any]]:
        """
        Parse XML using regex as a last resort.
        This is most lenient but also most prone to errors.
        """
        # Determine the tool name from the outermost tag
        tool_name_match = re.search(r'<([a-zA-Z0-9_]+)[>\\s]', xml_str)
        if not tool_name_match:
            raise ValueError("Could not determine tool name from XML string")
        
        tool_name = tool_name_match.group(1)
        params = {}
        
        # Extract parameters using a simple regex pattern - multiple strategies
        
        # Strategy 1: Look for standard <param>value</param> patterns
        param_pattern = r'<([a-zA-Z0-9_]+)>(.*?)</\1>'
        for match in re.finditer(param_pattern, xml_str, re.DOTALL):
            param_name = match.group(1)
            param_text = match.group(2).strip()
            
            # Skip if this is the tool name itself
            if param_name == tool_name:
                continue
            
            param_value = XmlToolCallParser._parse_parameter_value(param_text)
            params[param_name] = param_value
        
        # Strategy 2: Look for parameters on separate lines
        if not params:
            # Split by lines and find parameter patterns
            lines = xml_str.split('\n')
            current_param = None
            current_value = ""
            
            for line in lines:
                # Skip the tool opening/closing tag lines
                if re.match(fr'\s*<{tool_name}[>\s]', line) or re.match(fr'\s*</{tool_name}>', line):
                    continue
                    
                # Check if this line starts a new parameter
                param_start = re.match(r'\s*<([a-zA-Z0-9_]+)>\s*(.*)', line)
                if param_start:
                    # If we were collecting a previous parameter, save it
                    if current_param:
                        params[current_param] = XmlToolCallParser._parse_parameter_value(current_value.strip())
                    
                    # Start collecting a new parameter
                    current_param = param_start.group(1)
                    current_value = param_start.group(2)
                else:
                    # Continue collecting the current parameter value
                    if current_param:
                        current_value += " " + line.strip()
            
            # Don't forget the last parameter
            if current_param:
                params[current_param] = XmlToolCallParser._parse_parameter_value(current_value.strip())
        
        # Strategy 3: If still no params, try a more aggressive approach for very malformed XML
        if not params:
            # Try to extract parameters by finding all tag patterns
            all_tags = re.findall(r'<([a-zA-Z0-9_]+)>([^<]*)', xml_str)
            for tag, value in all_tags:
                if tag != tool_name:
                    params[tag] = XmlToolCallParser._parse_parameter_value(value.strip())
        
        return tool_name, params

    @staticmethod
    def _parse_parameter_value(param_text: str) -> Any:
        """
        Parse a parameter value, attempting to convert to Python types when appropriate.
        
        Args:
            param_text: The string representation of the parameter value
            
        Returns:
            The parsed value in the most appropriate Python type
        """
        # Try to parse as JSON first
        param_text = param_text.strip()
        try:
            # If it looks like JSON, try to parse it
            if (param_text.startswith('{') and param_text.endswith('}')) or \
               (param_text.startswith('[') and param_text.endswith(']')):
                return json.loads(param_text)
        except Exception as e:
            pass
            
        # Try to parse as boolean
        if param_text.lower() == 'true':
            return True
        elif param_text.lower() == 'false':
            return False
            
        # Try to parse as number
        try:
            # If it has a decimal, parse as float
            if '.' in param_text:
                return float(param_text)
            # Otherwise try parsing as int
            return int(param_text)
        except Exception as e:
            pass
            
        # Default to string
        return param_text
