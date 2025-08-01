from abc import ABC, abstractmethod
from utcp.client.utcp_client_config import UtcpClientConfig
from typing import Any
import os
import re
from utcp.client.utcp_client_config import UtcpVariableNotFound
from typing import List, Optional

class VariableSubstitutor(ABC):
    @abstractmethod
    def substitute(self, obj: Any, config: UtcpClientConfig, provider_name: Optional[str] = None) -> Any:
        pass

    @abstractmethod
    def find_required_variables(self, obj: Any, config: UtcpClientConfig, provider_name: Optional[str] = None) -> List[str]:
        pass
    
class DefaultVariableSubstitutor(VariableSubstitutor):
    def _get_variable(self, key: str, config: UtcpClientConfig, provider_name: Optional[str] = None) -> str:
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
