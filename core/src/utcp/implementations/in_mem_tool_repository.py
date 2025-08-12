from typing import List, Dict, Optional

from core.src.utcp.data.utcp_manual import UtcpManual
from utcp.python_specific_tooling.async_rwlock import AsyncRWLock
from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository

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

        # Manual name -> UtcpManual
        self._manuals: Dict[str, UtcpManual] = {}

        # Manual name -> CallTemplate
        self._manual_call_templates: Dict[str, CallTemplate] = {}

    async def save_manual(self, manual_call_template: CallTemplate, manual: UtcpManual) -> None:
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
        async with self._rwlock.read():
            return self._tools_by_name.get(tool_name)

    async def get_tools(self) -> List[Tool]:
        async with self._rwlock.read():
            return list(self._tools_by_name.values())

    async def get_tools_by_manual(self, manual_name: str) -> Optional[List[Tool]]:
        async with self._rwlock.read():
            manual = self._manuals.get(manual_name)
            return manual.tools if manual is not None else None

    async def get_manual(self, manual_name: str) -> Optional[UtcpManual]:
        async with self._rwlock.read():
            return self._manuals.get(manual_name)

    async def get_manuals(self) -> List[UtcpManual]:
        async with self._rwlock.read():
            return list(self._manuals.values())

    async def get_manual_call_template(self, manual_call_template_name: str) -> Optional[CallTemplate]:
        async with self._rwlock.read():
            return self._manual_call_templates.get(manual_call_template_name)

    async def get_manual_call_templates(self) -> List[CallTemplate]:
        async with self._rwlock.read():
            return list(self._manual_call_templates.values())
