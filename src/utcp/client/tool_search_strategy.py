"""Abstract interface for tool search strategies.

This module defines the contract for implementing tool search and ranking
algorithms. Different strategies can implement various approaches such as
tag-based search, semantic search, or hybrid approaches.
"""

from abc import ABC, abstractmethod
from typing import List
from utcp.shared.tool import Tool

class ToolSearchStrategy(ABC):
    """Abstract interface for tool search implementations.

    Defines the contract for tool search strategies that can be plugged into
    the UTCP client. Different implementations can provide various search
    algorithms such as tag-based matching, semantic similarity, or keyword
    search.

    Search strategies are responsible for:
    - Interpreting search queries
    - Ranking tools by relevance
    - Limiting results appropriately
    - Providing consistent search behavior
    """

    @abstractmethod
    async def search_tools(self, query: str, limit: int = 10) -> List[Tool]:
        """Search for tools relevant to the query.

        Executes a search against the available tools and returns the most
        relevant matches ranked by the strategy's scoring algorithm.

        Args:
            query: The search query string. Format depends on the strategy
                (e.g., keywords, tags, natural language).
            limit: Maximum number of tools to return. Use 0 for no limit.
                Strategies should respect this limit for performance.

        Returns:
            List of Tool objects ranked by relevance, limited to the
            specified count. Empty list if no matches found.

        Raises:
            ValueError: If the query format is invalid for this strategy.
            RuntimeError: If the search operation fails unexpectedly.
        """
        pass
