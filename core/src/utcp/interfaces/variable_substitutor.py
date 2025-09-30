from abc import ABC, abstractmethod
from typing import Any, Optional, List
from utcp.data.utcp_client_config import UtcpClientConfig

class VariableSubstitutor(ABC):
    """REQUIRED
    Abstract interface for variable substitution implementations.

    Defines the contract for variable substitution systems that can replace
    placeholders in configuration data with actual values from various sources.
    Implementations handle different variable resolution strategies and
    source hierarchies.
    """

    @abstractmethod
    def substitute(self, obj: dict | list | str, config: UtcpClientConfig, variable_namespace: Optional[str] = None) -> Any:
        """REQUIRED
        Substitute variables in the given object.

        Args:
            obj: Object containing potential variable references to substitute.
            config: UTCP client configuration containing variable definitions
                and loaders.
            variable_namespace: Optional variable namespace.

        Returns:
            Object with all variable references replaced by their values.

        Raises:
            UtcpVariableNotFound: If a referenced variable cannot be resolved.
        """
        pass

    @abstractmethod
    def find_required_variables(self, obj: dict | list | str, variable_namespace: Optional[str] = None) -> List[str]:
        """REQUIRED
        Find all variable references in the given object.

        Args:
            obj: Object to scan for variable references.
            variable_namespace: Optional variable namespace.

        Returns:
            List of fully-qualified variable names found in the object.
        """
        pass
