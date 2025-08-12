from typing import List, Dict, Optional

from utcp.implementations.async_rwlock import AsyncRWLock
from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool
from utcp.interfaces.tool_repository import ConcurrentToolRepository

class InMemToolRepository(ConcurrentToolRepository):
    """Thread-safe in-memory implementation of `ConcurrentToolRepository`.

    Stores tools and their associated manual call templates in dictionaries and
    protects all operations with a read-write lock to ensure consistency under
    concurrency while allowing multiple concurrent readers.
    """

    def __init__(self):
        # RW lock to allow concurrent reads and exclusive writes
        self._rwlock = AsyncRWLock()

        # Tool name -> Tool
        self._tools_by_name: Dict[str, Tool] = {}

        # Manual call template name -> List[Tool]
        self._tools_by_manual: Dict[str, List[Tool]] = {}

        # Manual call template name -> CallTemplate
        self._manuals_by_name: Dict[str, CallTemplate] = {}

    async def save_manual_call_template_with_tools(self, manual_call_template: CallTemplate, tools: List[Tool]) -> None:
        """Save a manual call template and replace its tools atomically."""
        async with self._rwlock.write():
            manual_name = manual_call_template.name

            # Remove old tools for this manual from the global index
            old_tools = self._tools_by_manual.get(manual_name, [])
            for t in old_tools:
                self._tools_by_name.pop(t.name, None)

            # Save/replace manual and its tools
            self._manuals_by_name[manual_name] = manual_call_template
            self._tools_by_manual[manual_name] = list(tools)

            # Index tools globally by name
            for t in tools:
                self._tools_by_name[t.name] = t

    async def remove_manual_call_template(self, manual_call_template_name: str) -> None:
        """Remove a manual call template and all its tools."""
        async with self._rwlock.write():
            if manual_call_template_name not in self._manuals_by_name:
                raise ValueError(f"Manual call template '{manual_call_template_name}' not found")

            # Remove tools of this manual
            for t in self._tools_by_manual.get(manual_call_template_name, []):
                self._tools_by_name.pop(t.name, None)

            # Remove manual and mapping
            self._tools_by_manual.pop(manual_call_template_name, None)
            self._manuals_by_name.pop(manual_call_template_name, None)

    async def remove_tool(self, tool_name: str) -> None:
        """Remove a single tool by name from the repository.

        If the tool is part of a manual's tool list, it will be removed from that list as well.
        """
        async with self._rwlock.write():
            tool = self._tools_by_name.pop(tool_name, None)
            if tool is None:
                raise ValueError(f"Tool '{tool_name}' not found")

            # Remove from any manual lists
            for manual, lst in list(self._tools_by_manual.items()):
                if lst:
                    self._tools_by_manual[manual] = [t for t in lst if t.name != tool_name]

    async def get_tool(self, tool_name: str) -> Optional[Tool]:
        async with self._rwlock.read():
            return self._tools_by_name.get(tool_name)

    async def get_tools(self) -> List[Tool]:
        async with self._rwlock.read():
            return list(self._tools_by_name.values())

    async def get_tools_by_manual_call_template(self, manual_call_template_name: str) -> Optional[List[Tool]]:
        async with self._rwlock.read():
            tools = self._tools_by_manual.get(manual_call_template_name)
            return list(tools) if tools is not None else None

    async def get_manual_call_template(self, manual_call_template_name: str) -> Optional[CallTemplate]:
        async with self._rwlock.read():
            return self._manuals_by_name.get(manual_call_template_name)

    async def get_manual_call_templates(self) -> List[CallTemplate]:
        async with self._rwlock.read():
            return list(self._manuals_by_name.values())
