"""Abstract interface for UTCP client transport implementations.

This module defines the contract that all transport implementations must follow
to integrate with the UTCP client. Transport implementations handle the actual
communication with different types of tool providers (HTTP, CLI, WebSocket, etc.).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, AsyncGenerator, TYPE_CHECKING

from utcp.data.register_manual_response import RegisterManualResult
from utcp.data.call_template import CallTemplate
if TYPE_CHECKING:
    from utcp.utcp_client import UtcpClient

class CommunicationProtocol(ABC):
    """Abstract interface for UTCP client transport implementations.

    Defines the contract that all transport implementations must follow to
    integrate with the UTCP client. Each transport handles communication
    with a specific type of provider (HTTP, CLI, WebSocket, etc.).

    Transport implementations are responsible for:
    - Discovering available tools from providers
    - Managing provider lifecycle (registration/deregistration)
    - Executing tool calls through the appropriate protocol
    """
    communication_protocols: Dict[str, 'CommunicationProtocol'] = {}

    @abstractmethod
    async def register_manual(self, caller: 'UtcpClient', manual_call_template: CallTemplate) -> RegisterManualResult:
        """Register a manual and its tools.

        Connects to the provider and retrieves the list of tools it offers.
        This may involve making discovery requests, parsing configuration files,
        or initializing connections depending on the provider type.

        Args:
            caller: The UTCP client that is calling this method.
            manual_call_template: The call template of the manual to register.

        Returns:
            RegisterManualResult object containing the call template and manual.

        Raises:
            ConnectionError: If unable to connect to the provider.
            ValueError: If the provider configuration is invalid.
        """
        pass

    @abstractmethod
    async def deregister_manual(self, caller: 'UtcpClient', manual_call_template: CallTemplate) -> None:
        """Deregister a manual and its tools.

        Cleanly disconnects from the provider and releases any associated
        resources such as connections, processes, or file handles.

        Args:
            caller: The UTCP client that is calling this method.
            manual_call_template: The call template of the manual to deregister.

        Note:
            Should handle cases where the provider is already disconnected
            or was never properly registered.
        """
        pass

    @abstractmethod
    async def call_tool(self, caller: 'UtcpClient', tool_name: str, arguments: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        """Execute a tool call through this transport.

        Sends a tool invocation request to the provider using the appropriate
        protocol and returns the result. Handles serialization of arguments
        and deserialization of responses according to the transport type.

        Args:
            caller: The UTCP client that is calling this method.
            tool_name: Name of the tool to call (may include provider prefix).
            arguments: Dictionary of arguments to pass to the tool.
            tool_call_template: Call template of the tool to call.

        Returns:
            The tool's response, with type depending on the tool's output schema.

        Raises:
            ToolNotFoundError: If the specified tool doesn't exist.
            ValidationError: If the arguments don't match the tool's input schema.
            ConnectionError: If unable to communicate with the provider.
            TimeoutError: If the tool call exceeds the configured timeout.
        """
        pass

    @abstractmethod
    async def call_tool_streaming(self, caller: 'UtcpClient', tool_name: str, arguments: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any]:
        """Execute a tool call through this transport streamingly.

        Sends a tool invocation request to the provider using the appropriate
        protocol and returns the result. Handles serialization of arguments
        and deserialization of responses according to the transport type.

        Args:
            caller: The UTCP client that is calling this method.
            tool_name: Name of the tool to call (may include provider prefix).
            arguments: Dictionary of arguments to pass to the tool.
            tool_call_template: Call template of the tool to call.

        Returns:
            An async generator that yields the tool's response, with type depending on the tool's output schema.

        Raises:
            ToolNotFoundError: If the specified tool doesn't exist.
            ValidationError: If the arguments don't match the tool's input schema.
            ConnectionError: If unable to communicate with the provider.
            TimeoutError: If the tool call exceeds the configured timeout.
        """
        pass
