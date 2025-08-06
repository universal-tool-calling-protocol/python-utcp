"""Main UTCP client implementation.

This module provides the primary client interface for the Universal Tool Calling
Protocol. The UtcpClient class manages multiple transport implementations,
tool repositories, search strategies, and provider configurations.

Key Features:
    - Multi-transport support (HTTP, CLI, WebSocket, etc.)
    - Dynamic provider registration and deregistration
    - Tool discovery and search capabilities
    - Variable substitution for configuration
    - Pluggable tool repositories and search strategies
"""

from pathlib import Path
import re
import os
import json
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union, Optional
from utcp.shared.tool import Tool
from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.client.transport_interfaces.http_transport import HttpClientTransport
from utcp.client.transport_interfaces.cli_transport import CliTransport
from utcp.client.transport_interfaces.sse_transport import SSEClientTransport
from utcp.client.transport_interfaces.streamable_http_transport import StreamableHttpClientTransport
from utcp.client.transport_interfaces.mcp_transport import MCPTransport
from utcp.client.transport_interfaces.text_transport import TextTransport
from utcp.client.transport_interfaces.graphql_transport import GraphQLClientTransport
from utcp.client.transport_interfaces.tcp_transport import TCPTransport
from utcp.client.transport_interfaces.udp_transport import UDPTransport
from utcp.client.utcp_client_config import UtcpClientConfig, UtcpVariableNotFound
from utcp.client.tool_repository import ToolRepository
from utcp.client.tool_repositories.in_mem_tool_repository import InMemToolRepository
from utcp.client.tool_search_strategies.tag_search import TagSearchStrategy
from utcp.client.tool_search_strategy import ToolSearchStrategy
from utcp.shared.provider import Provider, HttpProvider, CliProvider, SSEProvider, \
    StreamableHttpProvider, WebSocketProvider, GRPCProvider, GraphQLProvider, \
    TCPProvider, UDPProvider, WebRTCProvider, MCPProvider, TextProvider
from utcp.client.variable_substitutor import DefaultVariableSubstitutor, VariableSubstitutor

class UtcpClientInterface(ABC):
    """Abstract interface for UTCP client implementations.

    Defines the core contract for UTCP clients, including provider management,
    tool execution, search capabilities, and variable handling. This interface
    allows for different client implementations while maintaining consistency.

    The interface supports:
    - Provider lifecycle management (register/deregister)
    - Tool discovery and execution
    - Tool search and filtering
    - Configuration variable validation
    """
    @abstractmethod
    def register_tool_provider(self, manual_provider: Provider) -> List[Tool]:
        """
        Register a tool provider and its tools.

        Args:
            manual_provider: The provider to register.

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

    @abstractmethod
    def get_required_variables_for_manual_and_tools(self, manual_provider: Provider) -> List[str]:
        """
        Get the required variables for a manual provider and its tools.

        Args:
            manual_provider: The manual provider.

        Returns:
            A list of required variables for the manual provider and its tools.
        """
        pass

    @abstractmethod
    def get_required_variables_for_tool(self, tool_name: str) -> List[str]:
        """
        Get the required variables for a registered tool.

        Args:
            tool_name: The name of a registered tool.

        Returns:
            A list of required variables for the tool.
        """
        pass

class UtcpClient(UtcpClientInterface):
    """Main implementation of the UTCP client.

    The UtcpClient is the primary entry point for interacting with UTCP tool
    providers. It manages multiple transport implementations, handles provider
    registration, executes tool calls, and provides search capabilities.

    Key Features:
        - Multi-transport architecture supporting HTTP, CLI, WebSocket, etc.
        - Dynamic provider registration from configuration files
        - Variable substitution for secure credential management
        - Pluggable tool repositories and search strategies
        - Comprehensive error handling and validation

    Architecture:
        - Transport Layer: Handles protocol-specific communication
        - Repository Layer: Manages tool and provider storage
        - Search Layer: Provides tool discovery and filtering
        - Configuration Layer: Manages settings and variable substitution

    Usage:
        >>> client = await UtcpClient.create({
        ...     "providers_file_path": "./providers.json"
        ... })
        >>> tools = await client.search_tools("weather")
        >>> result = await client.call_tool("api.get_weather", {"city": "NYC"})

    Attributes:
        transports: Dictionary mapping provider types to transport implementations.
        tool_repository: Storage backend for tools and providers.
        search_strategy: Algorithm for tool search and ranking.
        config: Client configuration including file paths and settings.
        variable_substitutor: Handler for environment variable substitution.
    """
    
    transports: Dict[str, ClientTransportInterface] = {
        "http": HttpClientTransport(),
        "cli": CliTransport(),
        "sse": SSEClientTransport(),
        "http_stream": StreamableHttpClientTransport(),
        "mcp": MCPTransport(),
        "text": TextTransport(),
        "graphql": GraphQLClientTransport(),
        "tcp": TCPTransport(),
        "udp": UDPTransport(),
    }

    def __init__(self, config: UtcpClientConfig, tool_repository: ToolRepository, search_strategy: ToolSearchStrategy, variable_substitutor: VariableSubstitutor):
        """
        Use 'create' class method to create a new instance instead, as it supports loading UtcpClientConfig.
        """
        self.tool_repository = tool_repository
        self.search_strategy = search_strategy
        self.config = config
        self.variable_substitutor = variable_substitutor

    @classmethod
    async def create(cls, config: Optional[Union[Dict[str, Any], UtcpClientConfig]] = None, tool_repository: Optional[ToolRepository] = None, search_strategy: Optional[ToolSearchStrategy] = None) -> 'UtcpClient':
        """
        Create a new instance of UtcpClient.
        
        Args:
            config: The configuration for the client. Can be a dictionary or UtcpClientConfig object.
            tool_repository: The tool repository to use. Defaults to InMemToolRepository.
            search_strategy: The tool search strategy to use. Defaults to TagSearchStrategy.
        
        Returns:
            A new instance of UtcpClient.
        """
        if tool_repository is None:
            tool_repository = InMemToolRepository()
        if search_strategy is None:
            search_strategy = TagSearchStrategy(tool_repository)
        if config is None:
            config = UtcpClientConfig()
        elif isinstance(config, dict):
            config = UtcpClientConfig.model_validate(config)

        client = cls(config, tool_repository, search_strategy, DefaultVariableSubstitutor())

        # If a providers file is used, configure TextTransport to resolve relative paths from its directory
        if config.providers_file_path:
            providers_dir = os.path.dirname(os.path.abspath(config.providers_file_path))
            client.transports["text"] = TextTransport(base_path=providers_dir)
        
        if client.config.variables:
            config_without_vars = client.config.model_copy()
            config_without_vars.variables = None
            client.config.variables = client.variable_substitutor.substitute(client.config.variables, config_without_vars)

        await client.load_providers(config.providers_file_path)
        
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
        
        providers_file_path = Path(providers_file_path).resolve()
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
        # Create tasks for parallel provider registration
        tasks = []
        for provider_data in providers_data:
            async def register_single_provider(provider_data=provider_data):
                try:
                    # Determine provider type from provider_type field
                    provider_type = provider_data.get('provider_type')
                    if not provider_type:
                        print(f"Warning: Provider entry is missing required 'provider_type' field, skipping: {provider_data}")
                        return None
                    
                    provider_class = provider_classes.get(provider_type)
                    if not provider_class:
                        print(f"Warning: Unsupported provider type: {provider_type}, skipping")
                        return None
                    
                    # Create provider object with Pydantic validation
                    provider = provider_class.model_validate(provider_data)
                    
                    # Apply variable substitution and register provider
                    tools = await self.register_tool_provider(provider)
                    print(f"Successfully registered provider '{provider.name}' with {len(tools)} tools")
                    return provider
                except Exception as e:
                    # Log the error but continue with other providers
                    provider_name = provider_data.get('name', 'unknown')
                    print(f"Error registering provider '{provider_name}': {str(e)}")
                    return None
            
            tasks.append(register_single_provider())
        
        # Wait for all tasks to complete and collect results
        results = await asyncio.gather(*tasks)
        registered_providers = [p for p in results if p is not None]
                
        return registered_providers
            
    def _substitute_provider_variables(self, provider: Provider, provider_name: Optional[str] = None) -> Provider:
        provider_dict = provider.model_dump()

        processed_dict = self.variable_substitutor.substitute(provider_dict, self.config, provider_name)
        return provider.__class__(**processed_dict)

    async def get_required_variables_for_manual_and_tools(self, manual_provider: Provider) -> List[str]:
        """
        Get the required variables for a manual provider and its tools.

        Args:
            manual_provider: The provider to validate.

        Returns:
            A list of required variables for the provider.

        Raises:
            ValueError: If the provider type is not supported.
            UtcpVariableNotFound: If a variable is not found in the environment or in the configuration.
        """
        manual_provider.name = re.sub(r'[^\w]', '_', manual_provider.name)
        variables_for_provider = self.variable_substitutor.find_required_variables(manual_provider.model_dump(), manual_provider.name)
        if len(variables_for_provider) > 0:
            try:
                manual_provider = self._substitute_provider_variables(manual_provider, manual_provider.name)
            except UtcpVariableNotFound as e:
                return variables_for_provider
            return variables_for_provider
        if manual_provider.provider_type not in self.transports:
            raise ValueError(f"Provider type not supported: {manual_provider.provider_type}")
        tools: List[Tool] = await self.transports[manual_provider.provider_type].register_tool_provider(manual_provider)
        for tool in tools:
            variables_for_provider.extend(self.variable_substitutor.find_required_variables(tool.tool_provider.model_dump(), manual_provider.name))
        return variables_for_provider

    async def get_required_variables_for_tool(self, tool_name: str) -> List[str]:
        """
        Get the required variables for a tool.

        Args:
            tool_name: The name of the tool to validate.

        Returns:
            A list of required variables for the tool.

        Raises:
            ValueError: If the provider type is not supported.
            UtcpVariableNotFound: If a variable is not found in the environment or in the configuration.
        """
        provider_name = tool_name.split(".")[0]
        tool = await self.tool_repository.get_tool(tool_name)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")
        return self.variable_substitutor.find_required_variables(tool.tool_provider.model_dump(), provider_name)

    async def register_tool_provider(self, manual_provider: Provider) -> List[Tool]:
        """
        Register a tool provider.

        Args:
            manual_provider: The provider to register.

        Returns:
            A list of tools registered by the provider.

        Raises:
            ValueError: If the provider type is not supported.
            UtcpVariableNotFound: If a variable is not found in the environment or in the configuration.
        """
        # Replace all non-word characters with underscore
        manual_provider.name = re.sub(r'[^\w]', '_', manual_provider.name)
        if await self.tool_repository.get_provider(manual_provider.name) is not None:
            raise ValueError(f"Provider {manual_provider.name} already registered, please use a different name or deregister the existing provider")
        manual_provider = self._substitute_provider_variables(manual_provider, manual_provider.name)
        if manual_provider.provider_type not in self.transports:
            raise ValueError(f"Provider type not supported: {manual_provider.provider_type}")
        tools: List[Tool] = await self.transports[manual_provider.provider_type].register_tool_provider(manual_provider)
        for tool in tools:
            if not tool.name.startswith(manual_provider.name + "."):
                tool.name = manual_provider.name + "." + tool.name
        await self.tool_repository.save_provider_with_tools(manual_provider, tools)
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
        manual_provider_name = tool_name.split(".")[0]
        manual_provider = await self.tool_repository.get_provider(manual_provider_name)
        if manual_provider is None:
            raise ValueError(f"Provider not found: {manual_provider_name}")
        tool = await self.tool_repository.get_tool(tool_name)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")

        tool_provider = tool.tool_provider

        tool_provider = self._substitute_provider_variables(tool_provider, manual_provider_name)

        return await self.transports[tool_provider.provider_type].call_tool(tool_name, arguments, tool_provider)

    async def search_tools(self, query: str, limit: int = 10) -> List[Tool]:
        return await self.search_strategy.search_tools(query, limit)
