"""OpenAPI specification converter for UTCP tool generation.

This module provides functionality to convert OpenAPI specifications (both 2.0
and 3.0) into UTCP tool definitions. It handles schema resolution, authentication
mapping, and proper tool creation from REST API specifications.

Key Features:
    - OpenAPI 2.0 and 3.0 specification support
    - Automatic JSON reference ($ref) resolution
    - Authentication scheme mapping (API key, Basic, OAuth2)
    - Input/output schema extraction from OpenAPI schemas
    - URL path parameter handling
    - Request body and header field mapping
    - Provider name generation from specification metadata

The converter creates UTCP tools that can be used to interact with REST APIs
defined by OpenAPI specifications, providing a bridge between OpenAPI and UTCP.
"""

import json
from typing import Any, Dict, List, Optional, Tuple
import sys
import uuid
from urllib.parse import urlparse
from utcp.data.auth import Auth
from utcp.data.auth_implementations import ApiKeyAuth, BasicAuth, OAuth2Auth
from utcp.data.utcp_manual import UtcpManual
from utcp.data.tool import Tool, JsonSchema
from utcp_http.http_call_template import HttpCallTemplate

class OpenApiConverter:
    """Converts OpenAPI specifications into UTCP tool definitions.

    Processes OpenAPI 2.0 and 3.0 specifications to generate equivalent UTCP
    tools, handling schema resolution, authentication mapping, and proper
    HTTP call_template configuration. Each operation in the OpenAPI spec becomes
    a UTCP tool with appropriate input/output schemas.

    Features:
        - Complete OpenAPI specification parsing
        - Recursive JSON reference ($ref) resolution
        - Authentication scheme conversion (API key, Basic, OAuth2)
        - Input parameter and request body handling
        - Response schema extraction
        - URL template and path parameter support
        - Provider name normalization
        - Placeholder variable generation for configuration

    Architecture:
        The converter works by iterating through all paths and operations
        in the OpenAPI spec, extracting relevant information for each
        operation, and creating corresponding UTCP tools with HTTP call_templates.

    Attributes:
        spec: The parsed OpenAPI specification dictionary.
        spec_url: Optional URL where the specification was retrieved from.
        placeholder_counter: Counter for generating unique placeholder variables.
        call_template_name: Normalized name for the call_template derived from the spec.
    """

    def __init__(self, openapi_spec: Dict[str, Any], spec_url: Optional[str] = None, call_template_name: Optional[str] = None):
        """Initialize the OpenAPI converter.

        Args:
            openapi_spec: Parsed OpenAPI specification as a dictionary.
            spec_url: Optional URL where the specification was retrieved from.
                Used for base URL determination if servers are not specified.
            call_template_name: Optional custom name for the call_template. If not
                provided, derives name from the specification title.
        """
        self.spec = openapi_spec
        self.spec_url = spec_url
        # Single counter for all placeholder variables
        self.placeholder_counter = 0
        # If call_template_name is None then get the first word in spec.info.title
        if call_template_name is None:
            title = openapi_spec.get("info", {}).get("title", "openapi_call_template_" + uuid.uuid4().hex)
            # Replace characters that are invalid for identifiers
            invalid_chars = " -.,!?'\"\\/()[]{}#@$%^&*+=~`|;:<>"
            self.call_template_name = ''.join('_' if c in invalid_chars else c for c in title)
        else:
            self.call_template_name = call_template_name
            
    def _increment_placeholder_counter(self) -> int:
        """Increments the global counter and returns the new value.
            
        Returns:
            The new counter value after incrementing
        """
        self.placeholder_counter += 1
        return self.placeholder_counter
    
    def _get_placeholder(self, placeholder_name: str) -> str:
        """Returns a placeholder string using the current counter value.
        
        Args:
            placeholder_name: The name of the placeholder variable
        """
        return f"${{{placeholder_name}_{self.placeholder_counter}}}"

    def convert(self) -> UtcpManual:
        """Parses the OpenAPI specification and returns a UtcpManual."""
        self.placeholder_counter = 0
        tools = []
        servers = self.spec.get("servers")
        if servers:
            base_url = servers[0].get("url", "/")
        elif self.spec_url:
            parsed_url = urlparse(self.spec_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        else:
            # Fallback if no server info and no spec URL is provided
            base_url = "/"
            print("No server info or spec URL provided. Using fallback base URL: ", base_url, file=sys.stderr)

        for path, path_item in self.spec.get("paths", {}).items():
            for method, operation in path_item.items():
                if method.lower() in ['get', 'post', 'put', 'delete', 'patch']:
                    tool = self._create_tool(path, method, operation, base_url)
                    if tool:
                        tools.append(tool)

        return UtcpManual(tools=tools)

    def _extract_auth(self, operation: Dict[str, Any]) -> Optional[Auth]:
        """Extracts authentication information from OpenAPI operation and global security schemes."""
        # First check for operation-level security requirements
        security_requirements = operation.get("security", [])
        
        # If no operation-level security, check global security requirements
        if not security_requirements:
            security_requirements = self.spec.get("security", [])
        
        # If no security requirements, return None
        if not security_requirements:
            return None
        
        # Get security schemes - support both OpenAPI 2.0 and 3.0
        security_schemes = self._get_security_schemes()
        
        # Process the first security requirement (most common case)
        # Each security requirement is a dict with scheme name as key
        for security_req in security_requirements:
            for scheme_name, scopes in security_req.items():
                if scheme_name in security_schemes:
                    scheme = security_schemes[scheme_name]
                    return self._create_auth_from_scheme(scheme, scheme_name)
        
        return None
    
    def _get_security_schemes(self) -> Dict[str, Any]:
        """Gets security schemes supporting both OpenAPI 2.0 and 3.0."""
        # OpenAPI 3.0 format
        if "components" in self.spec:
            return self.spec.get("components", {}).get("securitySchemes", {})
        
        # OpenAPI 2.0 format
        return self.spec.get("securityDefinitions", {})

    def _resolve_ref_path(self, ref: str, visited: Optional[set] = None) -> Dict[str, Any]:
        """Resolves a JSON reference path like '#/components/schemas/X' with cycle detection.

        If a cycle is detected, returns a dict that preserves the original
        reference ({"$ref": ref}) instead of erasing it.
        """
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return {}
        visited = visited or set()
        if ref in visited:
            # Break cycles but keep the reference in place
            return {"$ref": ref}
        visited.add(ref)
        parts = ref[2:].split("/")
        node: Any = self.spec
        try:
            for part in parts:
                node = node[part]
            # Recursively resolve if nested $ref exists
            if isinstance(node, dict) and "$ref" in node:
                return self._resolve_ref_path(node["$ref"], visited)
            return node if isinstance(node, dict) else {}
        except Exception:
            return {}

    def _resolve_ref_obj(self, obj: Any, visited: Optional[set] = None) -> Any:
        """If obj is a $ref dict, resolves it; otherwise returns obj."""
        if isinstance(obj, dict) and "$ref" in obj:
            return self._resolve_ref_path(obj["$ref"], visited)
        return obj
    
    def _create_auth_from_scheme(self, scheme: Dict[str, Any], scheme_name: str) -> Optional[Auth]:
        """Creates an Auth object from an OpenAPI security scheme."""
        scheme_type = scheme.get("type", "").lower()

        if scheme_type == "apikey":
            # For API key auth, use the parameter name from the OpenAPI spec
            location = scheme.get("in", "header")  # Default to header if not specified
            param_name = scheme.get("name", "Authorization")  # Default name
            # Use the current counter value for the placeholder
            api_key_placeholder = self._get_placeholder("API_KEY")
            # Increment the counter after using it
            self._increment_placeholder_counter()
            return ApiKeyAuth(
                api_key=api_key_placeholder,
                var_name=param_name,
                location=location
            )
        
        elif scheme_type == "basic":
            # OpenAPI 2.0 format: type: basic
            # Use the current counter value for both placeholders
            username_placeholder = self._get_placeholder("USERNAME")
            password_placeholder = self._get_placeholder("PASSWORD")
            # Increment the counter after using it
            self._increment_placeholder_counter()
            return BasicAuth(
                username=username_placeholder,
                password=password_placeholder
            )
        
        elif scheme_type == "http":
            # OpenAPI 3.0 format: type: http with scheme
            http_scheme = scheme.get("scheme", "").lower()
            if http_scheme == "basic":
                # For basic auth, use conventional environment variable names
                # Use the current counter value for both placeholders
                username_placeholder = self._get_placeholder("USERNAME")
                password_placeholder = self._get_placeholder("PASSWORD")
                # Increment the counter after using it
                self._increment_placeholder_counter()
                return BasicAuth(
                    username=username_placeholder,
                    password=password_placeholder
                )
            elif http_scheme == "bearer":
                # Treat bearer tokens as API keys
                # Use the current counter value for the placeholder
                api_key_placeholder = self._get_placeholder("API_KEY")
                # Increment the counter after using it
                self._increment_placeholder_counter()
                return ApiKeyAuth(
                    api_key=f"Bearer {api_key_placeholder}",
                    var_name="Authorization",
                    location="header"
                )
        
        elif scheme_type == "oauth2":
            # Handle both OpenAPI 2.0 and 3.0 OAuth2 formats
            flows = scheme.get("flows", {})
            
            # OpenAPI 3.0 format
            if flows:
                for flow_type, flow_config in flows.items():
                    # Support both old and new flow names
                    if flow_type in ["authorizationCode", "accessCode", "clientCredentials", "application"]:
                        token_url = flow_config.get("tokenUrl")
                        if token_url:
                            # Use the current counter value for both placeholders
                            client_id_placeholder = self._get_placeholder("CLIENT_ID")
                            client_secret_placeholder = self._get_placeholder("CLIENT_SECRET")
                            # Increment the counter after using it
                            self._increment_placeholder_counter()
                            return OAuth2Auth(
                                token_url=token_url,
                                client_id=client_id_placeholder,
                                client_secret=client_secret_placeholder,
                                scope=" ".join(flow_config.get("scopes", {}).keys()) or None
                            )
            
            # OpenAPI 2.0 format (flows directly in scheme)
            else:
                flow_type = scheme.get("flow", "")
                token_url = scheme.get("tokenUrl")
                if token_url and flow_type in ["accessCode", "application", "clientCredentials"]:
                    # Use the current counter value for both placeholders
                    client_id_placeholder = self._get_placeholder("CLIENT_ID")
                    client_secret_placeholder = self._get_placeholder("CLIENT_SECRET")
                    # Increment the counter after using it
                    self._increment_placeholder_counter()
                    return OAuth2Auth(
                        token_url=token_url,
                        client_id=client_id_placeholder,
                        client_secret=client_secret_placeholder,
                        scope=" ".join(scheme.get("scopes", {}).keys()) or None
                    )
        
        return None

    def _create_tool(self, path: str, method: str, operation: Dict[str, Any], base_url: str) -> Optional[Tool]:
        """Creates a Tool object from an OpenAPI operation."""
        operation_id = operation.get("operationId")
        if not operation_id:
            return None

        description = operation.get("summary") or operation.get("description", "")
        tags = operation.get("tags", [])

        inputs, header_fields, body_field = self._extract_inputs(path, operation)
        outputs = self._extract_outputs(operation)
        auth = self._extract_auth(operation)

        call_template_name = self.spec.get("info", {}).get("title", "call_template_" + uuid.uuid4().hex)

        # Combine base URL and path, ensuring no double slashes
        full_url = base_url.rstrip('/') + '/' + path.lstrip('/')

        call_template = HttpCallTemplate(
            name=call_template_name,
            http_method=method.upper(),
            url=full_url,
            body_field=body_field if body_field else None,
            header_fields=header_fields if header_fields else None,
            auth=auth
        )

        return Tool(
            name=operation_id,
            description=description,
            inputs=inputs,
            outputs=outputs,
            tags=tags,
            tool_call_template=call_template
        )

    def _extract_inputs(self, path: str, operation: Dict[str, Any]) -> Tuple[JsonSchema, List[str], Optional[str]]:
        """Extracts input schema, header fields, and body field from an OpenAPI operation.

        - Merges path-level and operation-level parameters
        - Resolves $ref for parameters
        - Supports OpenAPI 2.0 body parameters and 3.0 requestBody
        """
        properties: Dict[str, Any] = {}
        required = []
        header_fields = []
        body_field = None

        # Merge path-level and operation-level parameters
        path_item = self.spec.get("paths", {}).get(path, {}) if path else {}
        all_params = []
        all_params.extend(path_item.get("parameters", []) or [])
        all_params.extend(operation.get("parameters", []) or [])

        # Handle parameters (query, header, path, cookie, body)
        for param in all_params:
            if isinstance(param, dict) and "$ref" in param:
                param = self._resolve_ref_path(param["$ref"], set()) or {}
            param_name = param.get("name")
            if not param_name:
                continue

            if param.get("in") == "header":
                header_fields.append(param_name)

            # OpenAPI 2.0 body parameter
            if param.get("in") == "body":
                body_field = "body"
                json_schema = self._resolve_ref_obj(param.get("schema", {}), set()) or {}
                properties[body_field] = {
                    "description": param.get("description", "Request body"),
                    **json_schema,
                }
                if param.get("required"):
                    required.append(body_field)
                continue

            # Non-body parameter
            schema = self._resolve_ref_obj(param.get("schema", {}), set()) or {}
            if not schema:
                # OpenAPI 2.0 non-body params use top-level type/items
                if "type" in param:
                    schema["type"] = param.get("type")
                if "items" in param:
                    schema["items"] = param.get("items")
                if "enum" in param:
                    schema["enum"] = param.get("enum")
            properties[param_name] = {
                "description": param.get("description", ""),
                **schema,
            }
            if param.get("required"):
                required.append(param_name)

        # Handle request body
        request_body = operation.get("requestBody")
        if request_body:
            content = request_body.get("content", {})
            json_schema = content.get("application/json", {}).get("schema")
            json_schema = self._resolve_ref_obj(json_schema, set()) if json_schema else None
            if json_schema:
                # Add a single 'body' field to represent the request body
                body_field = "body"
                properties[body_field] = {
                    "description": json_schema.get("description", "Request body"),
                    **json_schema
                }
                if json_schema.get("required"):
                    required.append(body_field)

        schema = JsonSchema(properties=properties, required=required if required else None)
        return schema, header_fields, body_field

    def _extract_outputs(self, operation: Dict[str, Any]) -> JsonSchema:
        """Extracts the output schema from an OpenAPI operation, resolving refs."""
        responses = operation.get("responses", {}) or {}
        success_response = responses.get("200") or responses.get("201") or responses.get("default")
        if not success_response:
            return JsonSchema()

        json_schema = None
        if "content" in success_response:
            content = success_response.get("content", {})
            json_schema = content.get("application/json", {}).get("schema")
            # Fallback to any content type if application/json missing
            if json_schema is None and isinstance(content, dict):
                for v in content.values():
                    if isinstance(v, dict) and "schema" in v:
                        json_schema = v.get("schema")
                        break
        elif "schema" in success_response:  # OpenAPI 2.0
            json_schema = success_response.get("schema")

        if not json_schema:
            return JsonSchema()

        # Resolve $ref in response schema
        json_schema = self._resolve_ref_obj(json_schema, set()) or {}

        schema_args = {
            "type": json_schema.get("type", "object"),
            "properties": json_schema.get("properties", {}),
            "required": json_schema.get("required"),
            "description": json_schema.get("description"),
            "title": json_schema.get("title"),
        }
        
        # Handle array item types
        if schema_args["type"] == "array" and "items" in json_schema:
            schema_args["items"] = json_schema.get("items")
            
        # Handle additional schema attributes
        for attr in ["enum", "minimum", "maximum", "format"]:
            if attr in json_schema:
                schema_args[attr] = json_schema.get(attr)
                
        return JsonSchema(**schema_args)
