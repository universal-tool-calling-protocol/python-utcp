import re
import os
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union, Optional
from utcp.shared.tool import Tool
from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.client.transport_interfaces.http_transport import HttpClientTransport
from utcp.client.utcp_client_config import UtcpClientConfig, UtcpVariableNotFound
from utcp.client.tool_repository import ToolRepository
from utcp.client.tool_repositories.in_mem_tool_repository import InMemToolRepository
from utcp.client.tool_search_strategies.tag_search import TagSearchStrategy
from utcp.client.tool_search_strategy import ToolSearchStrategy
from utcp.shared.provider import Provider, HttpProvider, CliProvider, SSEProvider, \
    StreamableHttpProvider, WebSocketProvider, GRPCProvider, GraphQLProvider, \
    TCPProvider, UDPProvider, WebRTCProvider, MCPProvider, TextProvider

class UtcpClientInterface(ABC):
    """
    Interface for a UTCP client.
    """
    @abstractmethod
    def register_tool_provider(self, provider: Provider) -> List[Tool]:
        """
        Register a tool provider and its tools.

        Args:
            provider: The provider to register.

        Returns:
            A list of tools associated with the provider.
        """
        pass
    
    @abstractmethod
    def deregister_tool_provider(self, provider_name: str) -> None:
        """
        Deregister a tool provider.

        Args:
            provider_name: The name of the provider to deregister.
        """
        pass
    
    @abstractmethod
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool.

        Args:
            tool_name: The name of the tool to call.
            arguments: The arguments to pass to the tool.

        Returns:
            The result of the tool call.
        """
        pass

    @abstractmethod
    def search_tools(self, query: str, limit: int = 10) -> List[Tool]:
        """
        Search for tools relevant to the query.

        Args:
            query: The search query.
            limit: The maximum number of tools to return. 0 for no limit.

        Returns:
            A list of tools that match the search query.
        """
        pass

class UtcpClient(UtcpClientInterface):
    transports: Dict[str, ClientTransportInterface] = {
        "http": HttpClientTransport()
    }

    def __init__(self, config: UtcpClientConfig, tool_repository: ToolRepository, search_strategy: ToolSearchStrategy):
        """
        Use 'create' class method to create a new instance instead, as it supports loading UtcpClientConfig.
        """
        self.tool_repository = tool_repository
        self.search_strategy = search_strategy
        self.config = config

    @classmethod
    async def create(cls, config: Optional[Union[Dict[str, Any], UtcpClientConfig]] = None, tool_repository: ToolRepository = InMemToolRepository(), search_strategy: Optional[ToolSearchStrategy] = None) -> 'UtcpClient':
        """
        Create a new instance of UtcpClient.
        
        Args:
            config: The configuration for the client. Can be a dictionary or UtcpClientConfig object.
            tool_repository: The tool repository to use. Defaults to InMemToolRepository.
            search_strategy: The tool search strategy to use. Defaults to TagSearchStrategy.
        
        Returns:
            A new instance of UtcpClient.
        """
        if search_strategy is None:
            search_strategy = TagSearchStrategy(tool_repository)
        if config is None:
            config = UtcpClientConfig()
        elif isinstance(config, dict):
            config = UtcpClientConfig.model_validate(config)

        client = cls(config, tool_repository, search_strategy)
        
        if client.config.variables:
            config_without_vars = client.config.model_copy()
            config_without_vars.variables = None
            client.config.variables = client._replace_vars_in_obj(client.config.variables, config_without_vars)

        providers = await client.load_providers(config.providers_file_path)
        for provider in providers:
            print(f"Registering provider '{provider.name}' with {len(provider.tools)} tools")
            try:
                await client.register_tool_provider(provider)
            except Exception as e:
                print(f"Error registering provider '{provider.name}': {str(e)}")
        
        return client

    async def load_providers(self, providers_file_path: str) -> List[Provider]:
        """Load providers from the file specified in the configuration.

        Returns:
            List of registered Provider objects.

        Raises:
            FileNotFoundError: If the providers file doesn't exist.
            ValueError: If the providers file contains invalid JSON.
            UtcpVariableNotFound: If a variable referenced in the provider configuration is not found.
        """
        if not providers_file_path:
            return []
        
        try:
            with open(providers_file_path, 'r') as f:
                providers_data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Providers file not found: {providers_file_path}")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON in providers file: {providers_file_path}")
        
        provider_classes = {
            'http': HttpProvider,
            'cli': CliProvider,
            'sse': SSEProvider,
            'http_stream': StreamableHttpProvider,
            'websocket': WebSocketProvider,
            'grpc': GRPCProvider,
            'graphql': GraphQLProvider,
            'tcp': TCPProvider,
            'udp': UDPProvider,
            'webrtc': WebRTCProvider,
            'mcp': MCPProvider,
            'text': TextProvider
        }
        
        if not isinstance(providers_data, list):
            raise ValueError(f"Providers file must contain a JSON array at the root level: {providers_file_path}")
        
        registered_providers = []
        for provider_data in providers_data:
            try:
                # Determine provider type from provider_type field
                provider_type = provider_data.get('provider_type')
                if not provider_type:
                    print(f"Warning: Provider entry is missing required 'provider_type' field, skipping: {provider_data}")
                    continue
                
                provider_class = provider_classes.get(provider_type)
                if not provider_class:
                    print(f"Warning: Unsupported provider type: {provider_type}, skipping")
                    continue
                
                # Create provider object with Pydantic validation
                provider = provider_class.model_validate(provider_data)
                
                # Apply variable substitution and register provider
                provider = self._substitute_provider_variables(provider)
                tools = await self.register_tool_provider(provider)
                registered_providers.append(provider)
                print(f"Successfully registered provider '{provider.name}' with {len(tools)} tools")
            except Exception as e:
                # Log the error but continue with other providers
                provider_name = provider_data.get('name', 'unknown')
                print(f"Error registering provider '{provider_name}': {str(e)}")
                
        return registered_providers
            
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

    def search_tools(self, query: str, limit: int = 10) -> List[Tool]:
        return self.search_strategy.search_tools(query, limit)
