import json
from typing import Any, Dict, List, Optional, Tuple
import sys
from utcp.shared.tool import Tool, ToolInputOutputSchema
from utcp.shared.utcp_manual import UtcpManual
from urllib.parse import urlparse

from utcp.shared.provider import HttpProvider
from utcp.shared.auth import Auth, ApiKeyAuth, BasicAuth, OAuth2Auth


class OpenApiConverter:
    """Converts an OpenAPI JSON specification into a UtcpManual."""

    def __init__(self, openapi_spec: Dict[str, Any], spec_url: Optional[str] = None, provider_name: Optional[str] = None):
        self.spec = openapi_spec
        self.spec_url = spec_url
        # If provider_name is None then get the first word in spec.info.title
        if provider_name is None:
            title = openapi_spec.get("info", {}).get("title", "openapi_provider")
            # Replace characters that are invalid for identifiers
            invalid_chars = " -.,!?'\"\\/()[]{}#@$%^&*+=~`|;:<>"
            self.provider_name = ''.join('_' if c in invalid_chars else c for c in title)
        else:
            self.provider_name = provider_name

    def convert(self) -> UtcpManual:
        """Parses the OpenAPI specification and returns a UtcpManual."""
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

    def _resolve_ref(self, ref: str) -> Dict[str, Any]:
        """Resolves a local JSON reference."""
        if not ref.startswith('#/'):
            raise ValueError(f"External or non-local references are not supported: {ref}")
        
        parts = ref[2:].split('/')
        node = self.spec
        for part in parts:
            try:
                node = node[part]
            except (KeyError, TypeError):
                raise ValueError(f"Reference not found: {ref}")
        return node

    def _resolve_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively resolves all $refs in a schema object."""
        if isinstance(schema, dict):
            if "$ref" in schema:
                resolved_ref = self._resolve_ref(schema["$ref"])
                # The resolved reference could itself contain refs, so we recurse
                return self._resolve_schema(resolved_ref)
            
            # Resolve refs in nested properties
            new_schema = {}
            for key, value in schema.items():
                new_schema[key] = self._resolve_schema(value)
            return new_schema
        
        if isinstance(schema, list):
            return [self._resolve_schema(item) for item in schema]

        return schema

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
    
    def _create_auth_from_scheme(self, scheme: Dict[str, Any], scheme_name: str) -> Optional[Auth]:
        """Creates an Auth object from an OpenAPI security scheme."""
        scheme_type = scheme.get("type", "").lower()

        if scheme_type == "apikey":
            # For API key auth, use the parameter name from the OpenAPI spec
            location = scheme.get("in", "header")  # Default to header if not specified
            param_name = scheme.get("name", "Authorization")  # Default name
            return ApiKeyAuth(
                api_key=f"${{{self.provider_name.upper()}_API_KEY}}",  # Placeholder for environment variable
                var_name=param_name,
                location=location
            )
        
        elif scheme_type == "basic":
            # OpenAPI 2.0 format: type: basic
            return BasicAuth(
                username=f"${{{self.provider_name.upper()}_USERNAME}}",
                password=f"${{{self.provider_name.upper()}_PASSWORD}}"
            )
        
        elif scheme_type == "http":
            # OpenAPI 3.0 format: type: http with scheme
            http_scheme = scheme.get("scheme", "").lower()
            if http_scheme == "basic":
                # For basic auth, use conventional environment variable names
                return BasicAuth(
                    username=f"${{{self.provider_name.upper()}_USERNAME}}",
                    password=f"${{{self.provider_name.upper()}_PASSWORD}}"
                )
            elif http_scheme == "bearer":
                # Treat bearer tokens as API keys
                return ApiKeyAuth(
                    api_key=f"Bearer ${{{self.provider_name.upper()}_API_KEY}}",
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
                            return OAuth2Auth(
                                token_url=token_url,
                                client_id=f"${{{self.provider_name.upper()}_CLIENT_ID}}",
                                client_secret=f"${{{self.provider_name.upper()}_CLIENT_SECRET}}",
                                scope=" ".join(flow_config.get("scopes", {}).keys()) or None
                            )
            
            # OpenAPI 2.0 format (flows directly in scheme)
            else:
                flow_type = scheme.get("flow", "")
                token_url = scheme.get("tokenUrl")
                if token_url and flow_type in ["accessCode", "application", "clientCredentials"]:
                    return OAuth2Auth(
                        token_url=token_url,
                        client_id=f"${{{self.provider_name.upper()}_CLIENT_ID}}",
                        client_secret=f"${{{self.provider_name.upper()}_CLIENT_SECRET}}",
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

        inputs, header_fields, body_field = self._extract_inputs(operation)
        outputs = self._extract_outputs(operation)
        auth = self._extract_auth(operation)

        provider_name = self.spec.get("info", {}).get("title", "openapi_provider")

        # Combine base URL and path, ensuring no double slashes
        full_url = base_url.rstrip('/') + '/' + path.lstrip('/')

        provider = HttpProvider(
            name=provider_name,
            provider_type="http",
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
            tool_provider=provider
        )

    def _extract_inputs(self, operation: Dict[str, Any]) -> Tuple[ToolInputOutputSchema, List[str], Optional[str]]:
        """Extracts input schema, header fields, and body field from an OpenAPI operation."""
        properties = {}
        required = []
        header_fields = []
        body_field = None

        # Handle parameters (query, header, path, cookie)
        for param in operation.get("parameters", []):
            param = self._resolve_schema(param)
            param_name = param.get("name")
            if not param_name:
                continue

            if param.get("in") == "header":
                header_fields.append(param_name)

            schema = self._resolve_schema(param.get("schema", {}))
            properties[param_name] = {
                "type": schema.get("type", "string"),
                "description": param.get("description", ""),
                **schema
            }
            if param.get("required"):
                required.append(param_name)

        # Handle request body
        request_body = operation.get("requestBody")
        if request_body:
            resolved_body = self._resolve_schema(request_body)
            content = resolved_body.get("content", {})
            json_schema = content.get("application/json", {}).get("schema")
            if json_schema:
                # Add a single 'body' field to represent the request body
                body_field = "body"
                properties[body_field] = {
                    "description": resolved_body.get("description", "Request body"),
                    **self._resolve_schema(json_schema)
                }
                if resolved_body.get("required"):
                    required.append(body_field)

        schema = ToolInputOutputSchema(properties=properties, required=required if required else None)
        return schema, header_fields, body_field

    def _extract_outputs(self, operation: Dict[str, Any]) -> ToolInputOutputSchema:
        """Extracts the output schema from an OpenAPI operation, resolving refs."""
        success_response = operation.get("responses", {}).get("200") or operation.get("responses", {}).get("201")
        if not success_response:
            return ToolInputOutputSchema()

        resolved_response = self._resolve_schema(success_response)
        content = resolved_response.get("content", {})
        json_schema = content.get("application/json", {}).get("schema")

        if not json_schema:
            return ToolInputOutputSchema()

        resolved_json_schema = self._resolve_schema(json_schema)
        schema_args = {
            "type": resolved_json_schema.get("type", "object"),
            "properties": resolved_json_schema.get("properties", {}),
            "required": resolved_json_schema.get("required"),
            "description": resolved_json_schema.get("description"),
            "title": resolved_json_schema.get("title"),
        }
        
        # Handle array item types
        if schema_args["type"] == "array" and "items" in resolved_json_schema:
            schema_args["items"] = resolved_json_schema.get("items")
            
        # Handle additional schema attributes
        for attr in ["enum", "minimum", "maximum", "format"]:
            if attr in resolved_json_schema:
                schema_args[attr] = resolved_json_schema.get(attr)
                
        return ToolInputOutputSchema(**schema_args)
