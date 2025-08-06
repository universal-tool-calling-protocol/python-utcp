"""Abstract interface for UTCP client transport implementations.

This module defines the contract that all transport implementations must follow
to integrate with the UTCP client. Transport implementations handle the actual
communication with different types of tool providers (HTTP, CLI, WebSocket, etc.).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from utcp.shared.provider import Provider
from utcp.shared.tool import Tool

class ClientTransportInterface(ABC):
    """Abstract interface for UTCP client transport implementations.

    Defines the contract that all transport implementations must follow to
    integrate with the UTCP client. Each transport handles communication
    with a specific type of provider (HTTP, CLI, WebSocket, etc.).

    Transport implementations are responsible for:
    - Discovering available tools from providers
    - Managing provider lifecycle (registration/deregistration)
    - Executing tool calls through the appropriate protocol
    """

    @abstractmethod
    async def register_tool_provider(self, manual_provider: Provider) -> List[Tool]:
        """Register a tool provider and discover its available tools.

        Connects to the provider and retrieves the list of tools it offers.
        This may involve making discovery requests, parsing configuration files,
        or initializing connections depending on the provider type.

        Args:
            manual_provider: The provider configuration to register.

        Returns:
            List of Tool objects discovered from the provider.

        Raises:
            ConnectionError: If unable to connect to the provider.
            ValueError: If the provider configuration is invalid.
        """
        pass

    @abstractmethod
    async def deregister_tool_provider(self, manual_provider: Provider) -> None:
        """Deregister a tool provider and clean up resources.

        Cleanly disconnects from the provider and releases any associated
        resources such as connections, processes, or file handles.

        Args:
            manual_provider: The provider configuration to deregister.

        Note:
            Should handle cases where the provider is already disconnected
            or was never properly registered.
        """
        pass

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], tool_provider: Provider) -> Any:
        """Execute a tool call through this transport.

        Sends a tool invocation request to the provider using the appropriate
        protocol and returns the result. Handles serialization of arguments
        and deserialization of responses according to the transport type.

        Args:
            tool_name: Name of the tool to call (may include provider prefix).
            arguments: Dictionary of arguments to pass to the tool.
            tool_provider: Provider configuration for the tool.

        Returns:
            The tool's response, with type depending on the tool's output schema.

        Raises:
            ToolNotFoundError: If the specified tool doesn't exist.
            ValidationError: If the arguments don't match the tool's input schema.
            ConnectionError: If unable to communicate with the provider.
            TimeoutError: If the tool call exceeds the configured timeout.
        """
        pass
