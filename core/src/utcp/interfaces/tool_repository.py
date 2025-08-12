"""Abstract interface for tool and provider storage.

This module defines the contract for implementing tool repositories that store
and manage UTCP tools and their associated providers. Different implementations
can provide various storage backends such as in-memory, database, or file-based
storage.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool

class ConcurrentToolRepository(ABC):
    """Abstract interface for tool and provider storage implementations.

    Defines the contract for repositories that manage the lifecycle and storage
    of UTCP tools and call templates. Repositories are responsible for:
    - Persisting provider configurations and their associated tools
    - Providing efficient lookup and retrieval operations
    - Managing relationships between call templates and tools
    - Ensuring data consistency during operations
    - Thread safety

    The repository interface supports both individual and bulk operations,
    allowing for flexible implementation strategies ranging from simple
    in-memory storage to sophisticated database backends.

    Note:
        All methods are async to support both synchronous and asynchronous
        storage implementations.
    """
    @abstractmethod
    async def save_manual_call_template_with_tools(self, manual_call_template: CallTemplate, tools: List[Tool]) -> None:
        """
        Save a manual call template and its tools in the repository.

        Args:
            manual_call_template: The call template associated with the manual to save.
            tools: The tools from the manual.
        """
        pass

    @abstractmethod
    async def remove_manual_call_template(self, manual_call_template_name: str) -> None:
        """
        Remove a manual call template and its tools from the repository.

        Args:
            manual_call_template_name: The name of the manual call template to remove.

        Raises:
            ValueError: If the manual call template is not found.
        """
        pass

    @abstractmethod
    async def remove_tool(self, tool_name: str) -> None:
        """
        Remove a tool from the repository.

        Args:
            tool_name: The name of the tool to remove.

        Raises:
            ValueError: If the tool is not found.
        """
        pass

    @abstractmethod
    async def get_tool(self, tool_name: str) -> Optional[Tool]:
        """
        Get a tool from the repository.

        Args:
            tool_name: The name of the tool to retrieve.

        Returns:
            The tool if found, otherwise None.
        """
        pass

    @abstractmethod
    async def get_tools(self) -> List[Tool]:
        """
        Get all tools from the repository.

        Returns:
            A list of tools.
        """
        pass
    
    @abstractmethod
    async def get_tools_by_manual_call_template(self, manual_call_template_name: str) -> Optional[List[Tool]]:
        """
        Get tools associated with a specific manual call template.

        Args:
            manual_call_template_name: The name of the manual call template.

        Returns:
            A list of tools associated with the manual call template, or None if the manual call template is not found.
        """
        pass

    @abstractmethod
    async def get_manual_call_template(self, manual_call_template_name: str) -> Optional[CallTemplate]:
        """
        Get a manual call template from the repository.

        Args:
            manual_call_template_name: The name of the manual call template to retrieve.

        Returns:
            The manual call template if found, otherwise None.
        """
        pass

    @abstractmethod
    async def get_manual_call_templates(self) -> List[CallTemplate]:
        """
        Get all manual call templates from the repository.

        Returns:
            A list of manual call templates.
        """
        pass
