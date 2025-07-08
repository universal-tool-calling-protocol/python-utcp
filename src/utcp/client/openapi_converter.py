import json
from typing import Any, Dict, List, Optional

from utcp.shared.tool import Tool, ToolInputOutputSchema
from utcp.shared.utcp_manual import UtcpManual
from utcp.shared.provider import HttpProvider


class OpenApiConverter:
    """Converts an OpenAPI JSON specification into a UtcpManual."""

    def __init__(self, openapi_spec: Dict[str, Any]):
        self.spec = openapi_spec

    def convert(self) -> UtcpManual:
        """Parses the OpenAPI specification and returns a UtcpManual."""
        tools = []
        servers = self.spec.get("servers", [{"url": "/"}])
        base_url = servers[0].get("url", "/")

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

    def _create_tool(self, path: str, method: str, operation: Dict[str, Any], base_url: str) -> Optional[Tool]:
        """Creates a Tool object from an OpenAPI operation."""
        operation_id = operation.get("operationId")
        if not operation_id:
            return None

        description = operation.get("summary") or operation.get("description", "")
        tags = operation.get("tags", [])

        inputs = self._extract_inputs(operation)
        outputs = self._extract_outputs(operation)

        provider_name = self.spec.get("info", {}).get("title", "openapi_provider")

        provider = HttpProvider(
            name=provider_name,
            provider_type="http",
            http_method=method.upper(),
            url=base_url,
            path=path
        )

        return Tool(
            name=operation_id,
            description=description,
            inputs=inputs,
            outputs=outputs,
            tags=tags,
            provider=provider
        )

    def _extract_inputs(self, operation: Dict[str, Any]) -> ToolInputOutputSchema:
        """Extracts the input schema from an OpenAPI operation, resolving refs."""
        properties = {}
        required = []

        # Handle parameters
        for param in operation.get("parameters", []):
            param = self._resolve_schema(param)
            param_name = param.get("name")
            if param_name:
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
                resolved_json_schema = self._resolve_schema(json_schema)
                if resolved_json_schema.get('type') == 'object' and 'properties' in resolved_json_schema:
                    properties.update(resolved_json_schema.get('properties', {}))
                    if 'required' in resolved_json_schema:
                        required.extend(resolved_json_schema['required'])

        return ToolInputOutputSchema(properties=properties, required=required if required else None)

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
        return ToolInputOutputSchema(
            type=resolved_json_schema.get("type", "object"),
            properties=resolved_json_schema.get("properties", {}),
            required=resolved_json_schema.get("required")
        )
