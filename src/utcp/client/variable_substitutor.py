"""Variable substitution system for UTCP configuration values.

This module provides a flexible variable substitution system that enables
dynamic replacement of placeholders in provider configurations and tool
arguments. It supports multiple variable sources including configuration
files, environment variables, and custom variable loaders.

Variable Syntax:
    Variables can be referenced using either ${VAR_NAME} or $VAR_NAME syntax.
    Provider-specific variables are automatically namespaced to avoid conflicts.
"""

from abc import ABC, abstractmethod
from utcp.client.utcp_client_config import UtcpClientConfig
from typing import Any
import os
import re
from utcp.client.utcp_client_config import UtcpVariableNotFound
from typing import List, Optional

class VariableSubstitutor(ABC):
    """Abstract interface for variable substitution implementations.

    Defines the contract for variable substitution systems that can replace
    placeholders in configuration data with actual values from various sources.
    Implementations handle different variable resolution strategies and
    source hierarchies.
    """

    @abstractmethod
    def substitute(self, obj: dict | list | str, config: UtcpClientConfig, provider_name: Optional[str] = None) -> Any:
        """Substitute variables in the given object.

        Args:
            obj: Object containing potential variable references to substitute.
                Can be dict, list, str, or any other type.
            config: UTCP client configuration containing variable definitions
                and loaders.
            provider_name: Optional provider name for variable namespacing.

        Returns:
            Object with all variable references replaced by their values.

        Raises:
            UtcpVariableNotFound: If a referenced variable cannot be resolved.
        """
        pass

    @abstractmethod
    def find_required_variables(self, obj: dict | list | str, provider_name: str) -> List[str]:
        """Find all variable references in the given object.

        Args:
            obj: Object to scan for variable references.
            provider_name: Provider name for variable namespacing.

        Returns:
            List of fully-qualified variable names found in the object.
        """
        pass
    
class DefaultVariableSubstitutor(VariableSubstitutor):
    """Default implementation of variable substitution.

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
    def _get_variable(self, key: str, config: UtcpClientConfig, provider_name: Optional[str] = None) -> str:
        """Resolve a variable value through the hierarchical resolution system.

        Searches for the variable value in the following order:
        1. Configuration variables dictionary
        2. Custom variable loaders (in registration order)
        3. Environment variables

        Args:
            key: Variable name to resolve.
            config: UTCP client configuration containing variable sources.
            provider_name: Optional provider name for variable namespacing.
                When provided, the key is prefixed with the provider name.

        Returns:
            Resolved variable value as a string.

        Raises:
            UtcpVariableNotFound: If the variable cannot be found in any source.
        """
        if provider_name:
            key = provider_name.replace("_", "!").replace("!", "__") + "_" + key
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
        
    def substitute(self, obj: dict | list | str, config: UtcpClientConfig, provider_name: Optional[str] = None) -> Any:
        """Recursively substitute variables in nested data structures.

        Performs deep substitution on dictionaries, lists, and strings.
        Non-string types are returned unchanged. String values are scanned
        for variable references using ${VAR} and $VAR syntax.

        Args:
            obj: Object to perform substitution on. Can be any type.
            config: UTCP client configuration containing variable sources.
            provider_name: Optional provider name for variable namespacing.

        Returns:
            Object with all variable references replaced. Structure and
            non-string values are preserved.

        Raises:
            UtcpVariableNotFound: If any referenced variable cannot be resolved.

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
        if isinstance(obj, dict):
            return {k: self.substitute(v, config, provider_name) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.substitute(elem, config, provider_name) for elem in obj]
        elif isinstance(obj, str):
            # Use a regular expression to find all variables in the string, supporting ${VAR} and $VAR formats
            def replacer(match):
                # The first group that is not None is the one that matched
                var_name = next((g for g in match.groups() if g is not None), "")
                return self._get_variable(var_name, config, provider_name)

            return re.sub(r'\${(\w+)}|\$(\w+)', replacer, obj)
        else:
            return obj

    def find_required_variables(self, obj: dict | list | str, provider_name: str) -> List[str]:
        """Recursively discover all variable references in a data structure.

        Scans the object for variable references using ${VAR} and $VAR syntax,
        returning fully-qualified variable names with provider namespacing.
        Useful for validation and dependency analysis.

        Args:
            obj: Object to scan for variable references.
            provider_name: Provider name used for variable namespacing.
                Variable names are prefixed with this provider name.

        Returns:
            List of fully-qualified variable names found in the object.
            Variables are prefixed with the provider name to avoid conflicts.

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
        if isinstance(obj, dict):
            result = []
            for v in obj.values():
                vars = self.find_required_variables(v, provider_name)
                result.extend(vars)
            return result
        elif isinstance(obj, list):
            result = []
            for elem in obj:
                vars = self.find_required_variables(elem, provider_name)
                result.extend(vars)
            return result
        elif isinstance(obj, str):
            # Find all variables in the string, supporting ${VAR} and $VAR formats
            variables = []
            pattern = r'\${(\w+)}|\$(\w+)'
            
            for match in re.finditer(pattern, obj):
                # The first group that is not None is the one that matched
                var_name = next(g for g in match.groups() if g is not None)
                full_var_name = provider_name.replace("_", "!").replace("!", "__") + "_" + var_name
                variables.append(full_var_name)
            
            return variables
        else:
            return []
