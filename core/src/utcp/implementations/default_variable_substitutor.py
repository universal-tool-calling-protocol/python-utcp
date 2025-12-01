"""Variable substitution system for UTCP configuration values.

This module provides a flexible variable substitution system that enables
dynamic replacement of placeholders in provider configurations and tool
arguments. It supports multiple variable sources including configuration
files, environment variables, and custom variable loaders.

Variable Syntax:
    Variables can be referenced using either ${VAR_NAME} or $VAR_NAME syntax.
    Provider-specific variables are automatically namespaced to avoid conflicts.
"""

from typing import Any
import os
import re
from utcp.exceptions import UtcpVariableNotFound
from typing import List, Optional
from utcp.interfaces.variable_substitutor import VariableSubstitutor
from utcp.data.utcp_client_config import UtcpClientConfig

class DefaultVariableSubstitutor(VariableSubstitutor):
    """REQUIRED
    Default implementation of variable substitution.

    Provides a hierarchical variable resolution system that searches for
    variables in the following order:
    1. Configuration variables (exact match)
    2. Custom variable loaders (in order)
    3. Environment variables

    Features:
        - Provider-specific variable namespacing
        - Multiple variable syntax support: ${VAR} and $VAR
        - Hierarchical variable resolution
        - Recursive substitution in nested data structures
        - Variable discovery for validation

    Variable Namespacing:
        Provider-specific variables are prefixed with the provider name
        to avoid conflicts. For example, a variable 'api_key' for provider
        'web_scraper' becomes 'web__scraper_api_key' internally.
    """
    def _get_variable(self, key: str, config: UtcpClientConfig, variable_namespace: Optional[str] = None) -> str:
        if variable_namespace:
            key = variable_namespace.replace("_", "!").replace("!", "__") + "_" + key
        if config.variables and key in config.variables:
            return config.variables[key]
        if config.load_variables_from:
            for var_loader in config.load_variables_from:
                var = var_loader.get(key)
                if var:
                    return var
        try:
            env_var = os.environ.get(key)
            if env_var:
                return env_var
        except Exception:
            pass
        
        raise UtcpVariableNotFound(key)
        
    def substitute(self, obj: dict | list | str, config: UtcpClientConfig, variable_namespace: Optional[str] = None) -> Any:
        """REQUIRED
        Recursively substitute variables in nested data structures.

        Performs deep substitution on dictionaries, lists, and strings.
        Non-string types are returned unchanged. String values are scanned
        for variable references using ${VAR} and $VAR syntax.

        Note:
            Strings containing '$ref' are skipped to support OpenAPI specs
            stored as string content, where $ref is a JSON reference keyword.

        Args:
            obj: Object to perform substitution on. Can be any type.
            config: UTCP client configuration containing variable sources.
            variable_namespace: Optional variable namespace.

        Returns:
            Object with all variable references replaced. Structure and
            non-string values are preserved.

        Raises:
            UtcpVariableNotFound: If any referenced variable cannot be resolved.
            ValueError: If variable_namespace contains invalid characters.

        Example:
            ```python
            substitutor = DefaultVariableSubstitutor()
            result = substitutor.substitute(
                {"url": "https://${HOST}/api", "port": 8080},
                config,
                "my_provider"
            )
            # Returns: {"url": "https://api.example.com/api", "port": 8080}
            ```
        """
        # Check that variable_namespace only contains alphanumeric characters or underscores
        if variable_namespace and not all(c.isalnum() or c == '_' for c in variable_namespace):
            raise ValueError(f"Variable namespace '{variable_namespace}' contains invalid characters. Only alphanumeric characters and underscores are allowed.")
        
        if isinstance(obj, str):
            # Skip substitution for JSON Schema $ref (but not variables like $refresh_token)
            if re.search(r'\$ref(?![a-zA-Z0-9_])', obj):
                return obj

            # Use a regular expression to find all variables in the string, supporting ${VAR} and $VAR formats
            def replacer(match):
                # The first group that is not None is the one that matched
                var_name = next((g for g in match.groups() if g is not None), "")
                return self._get_variable(var_name, config, variable_namespace)

            return re.sub(r'\${([a-zA-Z0-9_]+)}|\$([a-zA-Z0-9_]+)', replacer, obj)
        elif isinstance(obj, dict):
            return {k: self.substitute(v, config, variable_namespace) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.substitute(elem, config, variable_namespace) for elem in obj]
        else:
            return obj

    def find_required_variables(self, obj: dict | list | str, variable_namespace: Optional[str] = None) -> List[str]:
        """REQUIRED
        Recursively discover all variable references in a data structure.

        Scans the object for variable references using ${VAR} and $VAR syntax,
        returning fully-qualified variable names with variable namespacing.
        Useful for validation and dependency analysis.

        Note:
            Strings containing '$ref' are skipped to support OpenAPI specs
            stored as string content, where $ref is a JSON reference keyword.

        Args:
            obj: Object to scan for variable references.
            variable_namespace: Variable namespace used for variable namespacing.
                Variable names are prefixed with this variable namespace.

        Raises:
            ValueError: If variable_namespace contains invalid characters.

        Returns:
            List of unique fully-qualified variable names found in the object.

        Example:
            ```python
            substitutor = DefaultVariableSubstitutor()
            vars = substitutor.find_required_variables(
                {"url": "https://${HOST}/api", "key": "$API_KEY"},
                "web_api"
            )
            # Returns: ["web__api_HOST", "web__api_API_KEY"]
            ```
        """
        # Check that variable_namespace only contains alphanumeric characters or underscores
        if variable_namespace and not all(c.isalnum() or c == '_' for c in variable_namespace):
            raise ValueError(f"Variable namespace '{variable_namespace}' contains invalid characters. Only alphanumeric characters and underscores are allowed.")
        
        if isinstance(obj, dict):
            result = []
            for v in obj.values():
                vars = self.find_required_variables(v, variable_namespace)
                result.extend(vars)
            return result
        elif isinstance(obj, list):
            result = []
            for elem in obj:
                vars = self.find_required_variables(elem, variable_namespace)
                result.extend(vars)
            return result
        elif isinstance(obj, str):
            # Skip JSON Schema $ref (but not variables like $refresh_token)
            if re.search(r'\$ref(?![a-zA-Z0-9_])', obj):
                return []

            # Find all variables in the string, supporting ${VAR} and $VAR formats
            variables = []
            pattern = r'\${([a-zA-Z0-9_]+)}|\$([a-zA-Z0-9_]+)'
            
            for match in re.finditer(pattern, obj):
                # The first group that is not None is the one that matched
                var_name = next(g for g in match.groups() if g is not None)
                if variable_namespace:
                    full_var_name = variable_namespace.replace("_", "__") + "_" + var_name
                else:
                    full_var_name = var_name
                variables.append(full_var_name)
            
            return list(set(variables))
        else:
            return []
