import re
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Union
from utcp.shared.provider import Provider
from utcp.shared.tool import Tool
from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.client.transport_interfaces.http_transport import HttpClientTransport
from utcp.client.utcp_client_config import UtcpClientConfig, UtcpVariableNotFound
from utcp.client.utcp_tool_repository import UtcpToolRepository
from utcp.client.tool_repositories.in_mem_tool_repository import InMemToolRepository

class UtcpClientInterface(ABC):
    """
    Interface for a UTCP client.
    """
    @abstractmethod
    def register_tool_provider(self, provider: Provider) -> List[Tool]:
        pass
    
    @abstractmethod
    def deregister_tool_provider(self, provider_name: str) -> None:
        pass
    
    @abstractmethod
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        pass

class UtcpClient(UtcpClientInterface):
    transports: Dict[str, ClientTransportInterface] = {
        "http": HttpClientTransport()
    }

    def __init__(self, config: Union[Dict[str, Any], UtcpClientConfig] = None, tool_repository: UtcpToolRepository = InMemToolRepository()):
        self.tool_repository = tool_repository
        # Handle None by creating default config
        if config is None:
            self.config = UtcpClientConfig()
        # Convert dict to UtcpClientConfig if needed
        elif isinstance(config, dict):
            self.config = UtcpClientConfig.model_validate(config)
        # Use provided UtcpClientConfig directly
        else:
            self.config = config
            
        # Process variables if they exist
        if self.config.variables:
            config_without_vars = self.config.model_copy()
            config_without_vars.variables = None
            self.config.variables = self._replace_vars_in_obj(self.config.variables, config_without_vars)

    def _get_variable(self, key: str, config: UtcpClientConfig) -> str:
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
        
    def _replace_vars_in_obj(self, obj: Any, config: UtcpClientConfig) -> Any:
        if isinstance(obj, dict):
            return {k: self._replace_vars_in_obj(v, config) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_vars_in_obj(elem, config) for elem in obj]
        elif isinstance(obj, str):
            # Use a regular expression to find all variables in the string
            return re.sub(r'\$\{([^}]+)\}', lambda m: self._get_variable(m.group(1), config), obj)
        else:
            return obj

    def _substitute_provider_variables(self, provider: Provider) -> Provider:
        provider_dict = provider.model_dump()

        processed_dict = self._replace_vars_in_obj(provider_dict, self.config)
        return provider.__class__(**processed_dict)

    async def register_tool_provider(self, provider: Provider) -> List[Tool]:
        """
        Register a tool provider.

        Args:
            provider: The provider to register.

        Returns:
            A list of tools registered by the provider.

        Raises:
            ValueError: If the provider type is not supported.
            UtcpVariableNotFound: If a variable is not found in the environment or in the configuration.
        """
        provider = self._substitute_provider_variables(provider)
        if provider.provider_type not in self.transports:
            raise ValueError(f"Provider type not supported: {provider.provider_type}")
        tools: List[Tool] = await self.transports[provider.provider_type].register_tool_provider(provider)
        for tool in tools:
            if not tool.name.startswith(provider.name + "."):
                tool.name = provider.name + "." + tool.name
        await self.tool_repository.save_provider_with_tools(provider, tools)
        return tools

    async def deregister_tool_provider(self, provider_name: str) -> None:
        """
        Deregister a tool provider.

        Args:
            provider_name: The name of the provider to deregister.

        Raises:
            ValueError: If the provider is not found.
        """
        provider = await self.tool_repository.get_provider(provider_name)
        if provider is None:
            raise ValueError(f"Provider not found: {provider_name}")
        await self.transports[provider.provider_type].deregister_tool_provider(provider)
        await self.tool_repository.remove_provider(provider_name)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool.

        Args:
            tool_name: The name of the tool to call. Should be in the format provider_name.tool_name.
            arguments: The arguments to pass to the tool.

        Returns:
            The result of the tool.

        Raises:
            ValueError: If the tool is not found.
            UtcpVariableNotFound: If a variable is not found in the environment or in the configuration.
        """
        provider_name = tool_name.split(".")[0]
        provider = await self.tool_repository.get_provider(provider_name)
        if provider is None:
            raise ValueError(f"Provider not found: {provider_name}")
        tools = await self.tool_repository.get_tools_by_provider(provider_name)
        tool = next((t for t in tools if t.name == tool_name), None)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")

        tool_provider = tool.provider

        tool_provider = self._substitute_provider_variables(tool_provider)

        return await self.transports[tool_provider.provider_type].call_tool(tool_name, arguments, tool_provider)
