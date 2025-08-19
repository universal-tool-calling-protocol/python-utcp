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
from utcp.data.utcp_manual import UtcpManual
from utcp.interfaces.serializer import Serializer
from pydantic import BaseModel
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class ConcurrentToolRepository(BaseModel, ABC):
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
    tool_repository_type: str

    @abstractmethod
    async def save_manual(self, manual_call_template: CallTemplate, manual: UtcpManual) -> None:
        """
        Save a manual and its tools in the repository.

        Args:
            manual_call_template: The call template associated with the manual to save.
            manual: The manual to save.
        """
        pass

    @abstractmethod
    async def remove_manual(self, manual_name: str) -> bool:
        """
        Remove a manual and its tools from the repository.

        Args:
            manual_name: The name of the manual to remove.

        Returns:
            True if the manual was removed, False otherwise.
        """
        pass

    @abstractmethod
    async def remove_tool(self, tool_name: str) -> bool:
        """
        Remove a tool from the repository.

        Args:
            tool_name: The name of the tool to remove.

        Returns:
            True if the tool was removed, False otherwise.
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
    async def get_tools_by_manual(self, manual_name: str) -> Optional[List[Tool]]:
        """
        Get tools associated with a specific manual.

        Args:
            manual_name: The name of the manual.

        Returns:
            A list of tools associated with the manual, or None if the manual is not found.
        """
        pass

    @abstractmethod
    async def get_manual(self, manual_name: str) -> Optional[UtcpManual]:
        """
        Get a manual from the repository.

        Args:
            manual_name: The name of the manual to retrieve.

        Returns:
            The manual if found, otherwise None.
        """
        pass

    @abstractmethod
    async def get_manuals(self) -> List[UtcpManual]:
        """
        Get all manuals from the repository.

        Returns:
            A list of manuals.
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

class ConcurrentToolRepositoryConfigSerializer(Serializer[ConcurrentToolRepository]):
    tool_repository_implementations: Dict[str, Serializer['ConcurrentToolRepository']] = {}
    default_repository = "in_memory"

    def to_dict(self, obj: ConcurrentToolRepository) -> dict:
        return ConcurrentToolRepositoryConfigSerializer.tool_repository_implementations[obj.tool_repository_type].to_dict(obj)

    def validate_dict(self, data: dict) -> ConcurrentToolRepository:
        try:
            return ConcurrentToolRepositoryConfigSerializer.tool_repository_implementations[data['tool_repository_type']].validate_dict(data)
        except KeyError:
            raise ValueError(f"Invalid tool repository type: {data['tool_repository_type']}")
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid ConcurrentToolRepository: " + traceback.format_exc()) from e
