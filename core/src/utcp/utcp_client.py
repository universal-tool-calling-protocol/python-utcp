"""Main UTCP client implementation.

This module provides the primary client interface for the Universal Tool Calling
Protocol. The UtcpClient class manages multiple transport implementations,
tool repositories, search strategies, and CallTemplate configurations.

Key Features:
    - Multi-transport support (HTTP, CLI, WebSocket, etc.)
    - Dynamic CallTemplate registration and deregistration
    - Tool discovery and search capabilities
    - Variable substitution for configuration
    - Pluggable tool repositories and search strategies
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union, Optional, AsyncGenerator, TYPE_CHECKING

from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool
from utcp.data.register_manual_response import RegisterManualResult
from utcp.plugins.plugin_loader import ensure_plugins_initialized

if TYPE_CHECKING:
    from utcp.data.utcp_client_config import UtcpClientConfig

class UtcpClient(ABC):
    """Abstract interface for UTCP client implementations.

    Defines the core contract for UTCP clients, including CallTemplate management,
    tool execution, search capabilities, and variable handling. This interface
    allows for different client implementations while maintaining consistency.

    The interface supports:
    - CallTemplate lifecycle management (register/deregister)
    - Tool discovery and execution
    - Tool search and filtering
    - Configuration variable validation
    """

    def __init__(
        self,
        config: 'UtcpClientConfig',
        root_dir: Optional[str] = None,
    ):
        self.config = config
        self.root_dir = root_dir

    @classmethod
    async def create(
        cls,
        root_dir: Optional[str] = None,
        config: Optional[Union[str, Dict[str, Any], 'UtcpClientConfig']] = None,
    ) -> 'UtcpClient':
        """
        Create a new instance of UtcpClient.
        
        Args:
            root_dir: The root directory for the client to resolve relative paths from. Defaults to the current working directory.
            config: The configuration for the client. Can be a path to a configuration file, a dictionary, or UtcpClientConfig object.
            tool_repository: The tool repository to use. Defaults to InMemToolRepository.
            search_strategy: The tool search strategy to use. Defaults to TagSearchStrategy.
        
        Returns:
            A new instance of UtcpClient.
        """
        ensure_plugins_initialized()
        from utcp.implementations.utcp_client_implementation import UtcpClientImplementation
        return await UtcpClientImplementation.create(
            root_dir=root_dir,
            config=config
        )
    
    @abstractmethod
    async def register_manual(self, manual_call_template: CallTemplate) -> RegisterManualResult:
        """
        Register a tool CallTemplate and its tools.

        Args:
            manual_call_template: The CallTemplate to register.

        Returns:
            A RegisterManualResult object containing the registered CallTemplate and its tools.
        """
        pass

    @abstractmethod
    async def register_manuals(self, manual_call_templates: List[CallTemplate]) -> List[RegisterManualResult]:
        """
        Register multiple tool CallTemplates and their tools.

        Args:
            manual_call_templates: List of CallTemplates to register.

        Returns:
            A list of RegisterManualResult objects containing the registered CallTemplates and their tools. Order is not preserved.
        """
        pass
    
    @abstractmethod
    async def deregister_manual(self, manual_call_template_name: str) -> bool:
        """
        Deregister a tool CallTemplate.

        Args:
            manual_call_template_name: The name of the CallTemplate to deregister.

        Returns:
            True if the CallTemplate was deregistered, False otherwise.
        """
        pass
    
    @abstractmethod
    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Any:
        """
        Call a tool.

        Args:
            tool_name: The name of the tool to call.
            tool_args: The arguments to pass to the tool.

        Returns:
            The result of the tool call.
        """
        pass

    @abstractmethod
    async def call_tool_streaming(self, tool_name: str, tool_args: Dict[str, Any]) -> AsyncGenerator[Any, None]:
        """
        Call a tool streamingly.

        Args:
            tool_name: The name of the tool to call.
            tool_args: The arguments to pass to the tool.

        Returns:
            An async generator that yields the result of the tool call.
        """
        pass

    @abstractmethod
    async def search_tools(self, query: str, limit: int = 10, any_of_tags_required: Optional[List[str]] = None) -> List[Tool]:
        """
        Search for tools relevant to the query.

        Args:
            query: The search query.
            limit: The maximum number of tools to return. 0 for no limit.
            any_of_tags_required: Optional list of tags where one of them must be present in the tool's tags

        Returns:
            A list of tools that match the search query.
        """
        pass

    @abstractmethod
    async def get_required_variables_for_manual_and_tools(self, manual_call_template: CallTemplate) -> List[str]:
        """
        Get the required variables for a manual CallTemplate and its tools.

        Args:
            manual_call_template: The manual CallTemplate.

        Returns:
            A list of required variables for the manual CallTemplate and its tools.
        """
        pass

    @abstractmethod
    async def get_required_variables_for_registered_tool(self, tool_name: str) -> List[str]:
        """
        Get the required variables for a registered tool.

        Args:
            tool_name: The name of a registered tool.

        Returns:
            A list of required variables for the tool.
        """
        pass
