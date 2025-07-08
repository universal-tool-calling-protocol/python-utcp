from abc import ABC, abstractmethod
from typing import List
from utcp.shared.tool import Tool

class ToolSearchStrategy(ABC):
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
