"""OpenAPI specification converter for UTCP tool generation.

This module provides functionality to convert OpenAPI specifications (both 2.0
and 3.0) into UTCP tool definitions. It handles schema resolution, authentication
mapping, and proper tool creation from REST API specifications.

Key Features:
    - OpenAPI 2.0 and 3.0 specification support.
    - Automatic JSON reference ($ref) resolution.
    - Authentication scheme mapping (API key, Basic, OAuth2).
    - Input/output schema extraction from OpenAPI schemas.
    - URL path parameter handling.
    - Request body and header field mapping.
    - Call template name generation from specification metadata.

The converter creates UTCP tools that can be used to interact with REST APIs
defined by OpenAPI specifications, providing a bridge between OpenAPI and UTCP.
"""

import json
from typing import Any, Dict, List, Optional, Tuple, Literal, cast
import sys
import uuid
from urllib.parse import urljoin, urlparse
from utcp.data.auth import Auth
from utcp.data.auth_implementations import ApiKeyAuth, BasicAuth, OAuth2Auth
from utcp.data.utcp_manual import UtcpManual
from utcp.data.tool import Tool, JsonSchema
from utcp_http.http_call_template import HttpCallTemplate
from utcp_http._security import ensure_secure_url, is_loopback_url

# All HTTP methods that OpenAPI defines as operation fields on a Path Item
# Object. The conversion loop uses this to tell operations apart from the other
# path-item keys (parameters, summary, $ref, servers, ...), so that genuinely
# unsupported operations still reach _create_tool and get a warning rather than
# being silently dropped by the loop.
OPENAPI_OPERATION_METHODS: Tuple[str, ...] = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

# The subset of HTTP methods that HttpCallTemplate.http_method accepts.
# _create_tool validates against this and skips anything else with a warning.
SUPPORTED_HTTP_METHODS: Tuple[str, ...] = ("GET", "POST", "PUT", "DELETE", "PATCH")

class OpenApiConverter:
    """REQUIRED
    Converts OpenAPI specifications into UTCP tool definitions.

    Processes OpenAPI 2.0 and 3.0 specifications to generate equivalent UTCP
    tools, handling schema resolution, authentication mapping, and proper
    HTTP call_template configuration. Each operation in the OpenAPI spec becomes
    a UTCP tool with appropriate input/output schemas.

    Features:
        - Complete OpenAPI specification parsing.
        - Recursive JSON reference ($ref) resolution.
        - Authentication scheme conversion (API key, Basic, OAuth2).
        - Input parameter and request body handling.
        - Response schema extraction.
        - URL template and path parameter support.
        - Call template name normalization.
        - Placeholder variable generation for configuration.

    Usage Examples:
        Basic OpenAPI conversion:
        ```python
        from utcp_http.openapi_converter import OpenApiConverter

        # Assuming you have a method to fetch and parse the spec
        openapi_spec = fetch_and_parse_spec("https://api.example.com/openapi.json")

        converter = OpenApiConverter(openapi_spec)
        manual = converter.convert()

        # Use the generated manual with a UTCP client
        # client = await UtcpClient.create()
        # await client.register_manual(manual)
        ```

        Converting local OpenAPI file:
        ```python
        import yaml

        converter = OpenApiConverter()
        with open("api_spec.yaml", "r") as f:
            spec_content = yaml.safe_load(f)
        
        converter = OpenApiConverter(spec_content)
        manual = converter.convert()
        ```

    Architecture:
        The converter works by iterating through all paths and operations
        in the OpenAPI spec, extracting relevant information for each
        operation, and creating corresponding UTCP tools with HTTP call_templates.

    Attributes:
        spec: The parsed OpenAPI specification dictionary.
        spec_url: Optional URL where the specification was retrieved from.
        base_url: Optional base URL override for all API endpoints.
        placeholder_counter: Counter for generating unique placeholder variables.
        call_template_name: Normalized name for the call_template derived from the spec.
    """

    def __init__(self, openapi_spec: Dict[str, Any], spec_url: Optional[str] = None, call_template_name: Optional[str] = None, auth_tools: Optional[Auth] = None, base_url: Optional[str] = None):
        """Initializes the OpenAPI converter.

        Args:
            openapi_spec: Parsed OpenAPI specification as a dictionary.
            spec_url: Optional URL where the specification was retrieved from.
                Used for base URL determination if servers are not specified.
            call_template_name: Optional custom name for the call_template if
                the specification title is not provided.
            auth_tools: Optional auth configuration for generated tools.
                Applied only to endpoints that require authentication per OpenAPI spec.
            base_url: Optional base URL override for all API endpoints.
                When provided, this takes precedence over servers in the spec.
        """
        self.spec = openapi_spec
        self.spec_url = spec_url
        self.auth_tools = auth_tools
        self._base_url_override = base_url
        # Single counter for all placeholder variables
        self.placeholder_counter = 0
        if call_template_name is None:
            call_template_name = "openapi_call_template_" + uuid.uuid4().hex
        title = openapi_spec.get("info", {}).get("title", call_template_name)
        # Replace characters that are invalid for identifiers
        invalid_chars = " -.,!?'\"\\/()[]{}#@$%^&*+=~`|;:<>"
        self.call_template_name = ''.join('_' if c in invalid_chars else c for c in title)
            
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
        """REQUIRED
        Converts the loaded OpenAPI specification into a UtcpManual.

        This is the main entry point for the conversion process. It iterates through
        the paths and operations in the specification, creating a UTCP tool for each
        one.

        Returns:
            A UtcpManual object containing all the tools generated from the spec.
        """
        self.placeholder_counter = 0
        tools = []
        
        # Determine base URL: override > servers > spec_url > fallback
        if self._base_url_override:
            # Explicit override from UTCP config — caller has accepted the
            # trust decision, no further validation here.
            base_url = self._base_url_override
        elif self.spec.get("servers"):
            base_url = self.spec["servers"][0].get("url", "/")

            # Rule: a spec fetched from a non-loopback source cannot declare
            # a loopback server URL. A user pointing the converter at their
            # own localhost OpenAPI spec is allowed to declare loopback
            # servers, and an explicit ``base_url`` override always wins
            # (handled above).
            if (
                self.spec_url
                and not is_loopback_url(self.spec_url)
                and is_loopback_url(base_url)
            ):
                raise ValueError(
                    "Security error: OpenAPI spec fetched from "
                    f"{self.spec_url!r} declares a loopback server URL "
                    f"({base_url!r}). A remote spec is not allowed to "
                    "redirect tool calls at the agent's own loopback "
                    "interface — this is the SSRF pattern from "
                    "GHSA-39j6-4867-gg4w. If you trust this spec, set "
                    "the call template's ``base_url`` override "
                    "explicitly to bypass this check."
                )
        elif self.spec_url:
            parsed_url = urlparse(self.spec_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        else:
            # Fallback if no server info and no spec URL is provided
            base_url = "/"
            print("No server info or spec URL provided. Using fallback base URL: ", base_url, file=sys.stderr)

        for path, path_item in self.spec.get("paths", {}).items():
            for method, operation in path_item.items():
                if method.lower() in OPENAPI_OPERATION_METHODS:
                    tool = self._create_tool(path, method, operation, base_url)
                    if tool:
                        tools.append(tool)

        return UtcpManual(tools=tools)

    def _validate_token_url_eagerly(self, token_url: str) -> str:
        """Validate (and, when relative, resolve) an OpenAPI OAuth2
        ``tokenUrl`` at conversion time. Returns the absolute URL
        that should be embedded in the generated ``OAuth2Auth`` so
        the runtime check in ``_handle_oauth2`` sees a usable value
        instead of an unresolved relative reference. Backs
        GHSA-8cp3-qxj6-px34.

        OpenAPI 3.0 / 3.1 explicitly allow ``tokenUrl`` to be a
        relative reference resolved against the spec's own location.
        Behaviour:

          * Absolute URL: run ``ensure_secure_url`` and return as-is.
          * Relative URL with ``spec_url`` available: resolve against
            ``spec_url``, run ``ensure_secure_url`` on the resolved
            URL, and return the resolved URL so the runtime check
            (which doesn't have ``spec_url`` context) can validate it.
            This is also what closes the ``"tokenUrl": "//host/token"``
            scheme-relative bypass: the resolved URL inherits the
            spec's scheme.
          * Relative URL without ``spec_url``: cannot validate eagerly
            (no base to resolve against). Return the original string
            unchanged; the runtime check will reject it later.
        """
        parsed = urlparse(token_url)
        is_absolute = bool(parsed.scheme) and bool(parsed.netloc)

        if is_absolute:
            ensure_secure_url(token_url, context="OAuth2 tokenUrl in OpenAPI spec")
            return token_url

        if self.spec_url:
            try:
                resolved = urljoin(self.spec_url, token_url)
            except Exception:
                return token_url
            resolved_parsed = urlparse(resolved)
            if resolved_parsed.scheme and resolved_parsed.netloc:
                ensure_secure_url(
                    resolved,
                    context="OAuth2 tokenUrl in OpenAPI spec (resolved from relative URL)",
                )
                return resolved

        return token_url

    def _extract_auth(self, operation: Dict[str, Any]) -> Optional[Auth]:
        """
        Extracts authentication information from OpenAPI operation and global security schemes.
        Uses auth_tools configuration when compatible with OpenAPI auth requirements.
        Supports both OpenAPI 2.0 and 3.0 security schemes.
        """
        # First check for operation-level security requirements
        security_requirements = operation.get("security", [])
        
        # If no operation-level security, check global security requirements
        if not security_requirements:
            security_requirements = self.spec.get("security", [])
        
        # If no security requirements, return None (endpoint is public)
        if not security_requirements:
            return None
        
        # Generate auth from OpenAPI security schemes - support both OpenAPI 2.0 and 3.0
        security_schemes = self._get_security_schemes()
        
        # Process the first security requirement (most common case)
        # Each security requirement is a dict with scheme name as key
        for security_req in security_requirements:
            for scheme_name, scopes in security_req.items():
                if scheme_name in security_schemes:
                    scheme = security_schemes[scheme_name]
                    openapi_auth = self._create_auth_from_scheme(scheme, scheme_name)
                    
                    # If compatible with auth_tools, use actual values from manual call template
                    if self._is_auth_compatible(openapi_auth, self.auth_tools):
                        return self.auth_tools
                    else:
                        return openapi_auth  # Use placeholder from OpenAPI scheme
        
        return None

    def _is_auth_compatible(self, openapi_auth: Optional[Auth], auth_tools: Optional[Auth]) -> bool:
        """
        Checks if auth_tools configuration is compatible with OpenAPI auth requirements.
        
        Args:
            openapi_auth: Auth generated from OpenAPI security scheme
            auth_tools: Auth configuration from manual call template
            
        Returns:
            True if compatible and auth_tools should be used, False otherwise
        """
        if not openapi_auth or not auth_tools:
            return False
            
        # Must be same auth type
        if type(openapi_auth) != type(auth_tools):
            return False
            
        # For API Key auth, check header name and location compatibility
        if hasattr(openapi_auth, 'var_name') and hasattr(auth_tools, 'var_name'):
            openapi_var = getattr(openapi_auth, 'var_name', "").lower() if getattr(openapi_auth, 'var_name', None) else ""
            tools_var = getattr(auth_tools, 'var_name', "").lower() if getattr(auth_tools, 'var_name', None) else ""
            
            if openapi_var != tools_var:
                return False
                
            if hasattr(openapi_auth, 'location') and hasattr(auth_tools, 'location'):
                if getattr(openapi_auth, 'location', None) != getattr(auth_tools, 'location', None):
                    return False
        
        return True
    
    def _get_security_schemes(self) -> Dict[str, Any]:
        """
        Gets security schemes supporting both OpenAPI 2.0 and 3.0."""
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

    def _extract_examples(self, obj: Dict[str, Any]) -> Optional[List[Any]]:
        """
        Extract examples from an OpenAPI Parameter, Media Type, or Schema object.

        Handles all three shapes the spec allows:
          - 'example' (single value) - OpenAPI Parameter / Media Type / 3.0 Schema.
          - 'examples' as a map of named Example Objects - OpenAPI Parameter /
            Media Type Object (each entry carries an inline 'value').
          - 'examples' as a list of literal values - JSON Schema / OpenAPI 3.1
            Schema Object.

        Returns a list of example values suitable for JSON Schema 'examples' keyword.
        """
        examples = []

        # Handle single 'example' field
        if "example" in obj and obj["example"] is not None:
            examples.append(obj["example"])

        examples_obj = obj.get("examples")
        if isinstance(examples_obj, list):
            # JSON Schema / OpenAPI 3.1 Schema form: a plain list of example values.
            examples.extend(examples_obj)
        elif isinstance(examples_obj, dict):
            # OpenAPI 3.0 form: a map of named Example Objects.
            for example_obj in examples_obj.values():
                if isinstance(example_obj, dict) and "$ref" in example_obj:
                    example_obj = self._resolve_ref_obj(example_obj, set()) or {}
                if isinstance(example_obj, dict):
                    # Example Object can have 'value' or 'externalValue'
                    if "value" in example_obj:
                        examples.append(example_obj["value"])
                    # Note: externalValue is a URI reference, we skip it as it's not inline

        return examples if examples else None

    def _merge_examples(self, *objs: Optional[Dict[str, Any]]) -> Optional[List[Any]]:
        """
        Collect and de-duplicate examples from several OpenAPI objects, preserving order.

        Used to combine examples that can appear at more than one level for the
        same value, e.g. a Media Type Object and the Schema Object beneath it.
        Returns a list suitable for the JSON Schema 'examples' keyword, or None.

        De-duplication uses a canonical JSON serialization (sorted keys) as the
        identity. This is order-insensitive for objects and type-aware, so it
        does not collapse semantically distinct examples the way Python's ``==``
        would (``True == 1``, ``False == 0``, ``1 == 1.0``).
        """
        merged: List[Any] = []
        seen: set = set()
        for obj in objs:
            if not isinstance(obj, dict):
                continue
            for ex in self._extract_examples(obj) or []:
                key = json.dumps(ex, sort_keys=True, default=str)
                if key not in seen:
                    seen.add(key)
                    merged.append(ex)
        return merged or None

    @staticmethod
    def _schema_without_example_keys(schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a copy of a schema dict with the raw 'example'/'examples' keys removed.

        Examples are normalized into the JSON Schema 'examples' keyword via
        _merge_examples, so the raw OpenAPI keys must not be spread back onto the
        property or they would leak through as untyped extra fields.
        """
        return {k: v for k, v in schema.items() if k not in ("example", "examples")}
    
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
                            # Reject obviously-internal or plain-HTTP
                            # token URLs at conversion time AND resolve
                            # relative URLs against ``spec_url`` so the
                            # runtime check in ``_handle_oauth2`` sees
                            # an absolute URL (otherwise an OpenAPI
                            # 3.0 spec with ``"tokenUrl":
                            # "/oauth/token"`` would pass conversion
                            # but fail at runtime). Backs
                            # GHSA-8cp3-qxj6-px34.
                            token_url = self._validate_token_url_eagerly(token_url)
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
                    token_url = self._validate_token_url_eagerly(token_url)
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

        # Validate the HTTP method against what HttpCallTemplate accepts before
        # building the tool. OpenAPI allows operations like 'options'/'head'/
        # 'trace' that the call template's Literal type rejects; skip them with a
        # warning instead of letting Pydantic raise mid-conversion. This explicit
        # check is also what makes the cast below truthful rather than a blind
        # assertion.
        http_method = method.upper()
        if http_method not in SUPPORTED_HTTP_METHODS:
            print(
                f"Skipping operation '{operation_id}': unsupported HTTP method '{method}'.",
                file=sys.stderr,
            )
            return None

        description = operation.get("summary") or operation.get("description", "")
        tags = operation.get("tags", [])

        inputs, header_fields, body_field = self._extract_inputs(path, operation)
        outputs = self._extract_outputs(operation)
        auth = self._extract_auth(operation)

        # Combine base URL and path, ensuring no double slashes
        full_url = base_url.rstrip('/') + '/' + path.lstrip('/')

        call_template = HttpCallTemplate(
            name=self.call_template_name,
            http_method=cast(Literal["GET", "POST", "PUT", "DELETE", "PATCH"], http_method),
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

                # Examples can live on the parameter itself and on its schema;
                # collect both into the normalized 'examples' keyword.
                body_examples = self._merge_examples(param, json_schema)

                prop = {
                    "description": param.get("description", "Request body"),
                    **self._schema_without_example_keys(json_schema),
                }
                if body_examples:
                    prop["examples"] = body_examples

                properties[body_field] = prop
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
            
            # Examples can live on the parameter itself and on its schema;
            # collect both into the normalized 'examples' keyword.
            param_examples = self._merge_examples(param, schema)

            prop = {
                "description": param.get("description", ""),
                **self._schema_without_example_keys(schema),
            }
            if param_examples:
                prop["examples"] = param_examples

            properties[param_name] = prop
            if param.get("required"):
                required.append(param_name)

        # Handle request body
        request_body = operation.get("requestBody")
        if request_body:
            content = request_body.get("content", {})
            json_schema = content.get("application/json", {}).get("schema")
            json_schema = self._resolve_ref_obj(json_schema, set()) if json_schema else None
            
            # Examples can live on the media type object and on the schema;
            # collect both into the normalized 'examples' keyword.
            media_type_obj = content.get("application/json", {})

            if json_schema:
                body_examples = self._merge_examples(media_type_obj, json_schema)
                # Add a single 'body' field to represent the request body
                body_field = "body"
                prop = {
                    "description": json_schema.get("description", "Request body"),
                    **self._schema_without_example_keys(json_schema)
                }
                if body_examples:
                    prop["examples"] = body_examples

                properties[body_field] = prop
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
        media_type_obj = None
        if "content" in success_response:
            content = success_response.get("content", {})
            json_schema = content.get("application/json", {}).get("schema")
            media_type_obj = content.get("application/json", {})
            # Fallback to any content type if application/json missing
            if json_schema is None and isinstance(content, dict):
                for v in content.values():
                    if isinstance(v, dict) and "schema" in v:
                        json_schema = v.get("schema")
                        media_type_obj = v
                        break
        elif "schema" in success_response:  # OpenAPI 2.0
            json_schema = success_response.get("schema")

        if not json_schema:
            return JsonSchema()

        # Resolve $ref in response schema
        json_schema = self._resolve_ref_obj(json_schema, set()) or {}

        # Extract examples from response media type and schema level
        response_examples = self._merge_examples(media_type_obj, json_schema)

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
        
        # Add examples if present
        if response_examples:
            schema_args["examples"] = response_examples
                
        return JsonSchema(**schema_args)
