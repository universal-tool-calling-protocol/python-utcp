from typing import List, Dict, Optional

from utcp.data.utcp_manual import UtcpManual
from utcp.python_specific_tooling.async_rwlock import AsyncRWLock
from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository
from utcp.interfaces.serializer import Serializer

class InMemToolRepository(ConcurrentToolRepository):
    """REQUIRED
    Thread-safe in-memory implementation of `ConcurrentToolRepository`.

    Stores tools and their associated manual call templates in dictionaries and
    protects all operations with a read-write lock to ensure consistency under
    concurrency while allowing multiple concurrent readers.
    """

    def __init__(self):
        super().__init__(tool_repository_type="in_memory")
        # RW lock to allow concurrent reads and exclusive writes
        self._rwlock = AsyncRWLock()

        # Tool name -> Tool
        self._tools_by_name: Dict[str, Tool] = {}

        # Manual name -> UtcpManual
        self._manuals: Dict[str, UtcpManual] = {}

        # Manual name -> CallTemplate
        self._manual_call_templates: Dict[str, CallTemplate] = {}

    async def save_manual(self, manual_call_template: CallTemplate, manual: UtcpManual) -> None:
        """REQUIRED
        Save a manual and its associated tools.

        Args:
            manual_call_template: The manual call template to save.
            manual: The manual to save.
        """
        async with self._rwlock.write():
            manual_name = manual_call_template.name

            # Remove old tools for this manual from the global index
            old_manual = self._manuals.get(manual_name)
            if old_manual is not None:
                for t in old_manual.tools:
                    self._tools_by_name.pop(t.name, None)

            # Save/replace manual and its tools
            self._manual_call_templates[manual_name] = manual_call_template
            self._manuals[manual_name] = manual

            # Index tools globally by name
            for t in manual.tools:
                self._tools_by_name[t.name] = t

    async def remove_manual(self, manual_name: str) -> bool:
        """REQUIRED
        Remove a manual and its associated tools.

        Args:
            manual_name: The name of the manual to remove.

        Returns:
            True if the manual was removed, False otherwise.
        """
        async with self._rwlock.write():
            # Remove tools of this manual
            old_manual = self._manuals.get(manual_name)
            if old_manual is not None:
                for t in old_manual.tools:
                    self._tools_by_name.pop(t.name, None)
            else:
                return False

            # Remove manual and mapping
            self._manuals.pop(manual_name, None)
            self._manual_call_templates.pop(manual_name, None)
            return True

    async def remove_tool(self, tool_name: str) -> bool:
        """REQUIRED
        Remove a tool from the repository.

        Args:
            tool_name: The name of the tool to remove.

        Returns:
            True if the tool was removed, False otherwise.
        """
        async with self._rwlock.write():
            tool = self._tools_by_name.pop(tool_name, None)
            if tool is None:
                return False

            # Remove from any manual lists
            for manual in self._manuals.values():
                if tool in manual.tools:
                    manual.tools.remove(tool)
            return True

    async def get_tool(self, tool_name: str) -> Optional[Tool]:
        """REQUIRED
        Get a tool by name.

        Args:
            tool_name: The name of the tool to get.

        Returns:
            The tool if it exists, None otherwise.
        """
        async with self._rwlock.read():
            tool = self._tools_by_name.get(tool_name)
            return tool.model_copy(deep=True) if tool else None

    async def get_tools(self) -> List[Tool]:
        """REQUIRED
        Get all tools in the repository.

        Returns:
            A list of all tools in the repository.
        """
        async with self._rwlock.read():
            return [t.model_copy(deep=True) for t in self._tools_by_name.values()]

    async def get_tools_by_manual(self, manual_name: str) -> Optional[List[Tool]]:
        """REQUIRED
        Get all tools associated with a manual.

        Args:
            manual_name: The name of the manual to get tools for.

        Returns:
            A list of tools associated with the manual, or None if the manual does not exist.
        """
        async with self._rwlock.read():
            manual = self._manuals.get(manual_name)
            return [t.model_copy(deep=True) for t in manual.tools] if manual is not None else None

    async def get_manual(self, manual_name: str) -> Optional[UtcpManual]:
        """REQUIRED
        Get a manual by name.

        Args:
            manual_name: The name of the manual to get.

        Returns:
            The manual if it exists, None otherwise.
        """
        async with self._rwlock.read():
            manual = self._manuals.get(manual_name)
            return manual.model_copy(deep=True) if manual else None

    async def get_manuals(self) -> List[UtcpManual]:
        """REQUIRED
        Get all manuals in the repository.

        Returns:
            A list of all manuals in the repository.
        """
        async with self._rwlock.read():
            return [m.model_copy(deep=True) for m in self._manuals.values()]

    async def get_manual_call_template(self, manual_call_template_name: str) -> Optional[CallTemplate]:
        """REQUIRED
        Get a manual call template by name.

        Args:
            manual_call_template_name: The name of the manual call template to get.

        Returns:
            The manual call template if it exists, None otherwise.
        """
        async with self._rwlock.read():
            manual_call_template = self._manual_call_templates.get(manual_call_template_name)
            return manual_call_template.model_copy(deep=True) if manual_call_template else None

    async def get_manual_call_templates(self) -> List[CallTemplate]:
        """REQUIRED
        Get all manual call templates in the repository.

        Returns:
            A list of all manual call templates in the repository.
        """
        async with self._rwlock.read():
            return [m.model_copy(deep=True) for m in self._manual_call_templates.values()]

class InMemToolRepositoryConfigSerializer(Serializer[InMemToolRepository]):
    """REQUIRED
    Serializer for `InMemToolRepository`.

    Converts an `InMemToolRepository` instance to a dictionary and vice versa.
    """
    def to_dict(self, obj: InMemToolRepository) -> dict:
        """REQUIRED
        Convert an `InMemToolRepository` instance to a dictionary.

        Args:
            obj: The `InMemToolRepository` instance to convert.

        Returns:
            A dictionary representing the `InMemToolRepository` instance.
        """
        return {
            "tool_repository_type": obj.tool_repository_type,
        }

    def validate_dict(self, data: dict) -> InMemToolRepository:
        """REQUIRED
        Convert a dictionary to an `InMemToolRepository` instance.

        Args:
            data: The dictionary to convert.

        Returns:
            An `InMemToolRepository` instance representing the dictionary.
        """
        return InMemToolRepository()
