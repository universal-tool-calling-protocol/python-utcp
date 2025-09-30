"""Abstract interface for tool search strategies.

This module defines the contract for implementing tool search and ranking
algorithms. Different strategies can implement various approaches such as
tag-based search, semantic search, or hybrid approaches.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from utcp.data.tool import Tool
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository
from utcp.interfaces.serializer import Serializer
from pydantic import BaseModel
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class ToolSearchStrategy(BaseModel, ABC):
    """REQUIRED
    Abstract interface for tool search implementations.

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
    tool_search_strategy_type: str

    @abstractmethod
    async def search_tools(self, tool_repository: ConcurrentToolRepository, query: str, limit: int = 10, any_of_tags_required: Optional[List[str]] = None) -> List[Tool]:
        """REQUIRED
        Search for tools relevant to the query.

        Executes a search against the available tools and returns the most
        relevant matches ranked by the strategy's scoring algorithm.

        Args:
            tool_repository: The tool repository to search within.
            query: The search query string. Format depends on the strategy
                (e.g., keywords, tags, natural language).
            limit: Maximum number of tools to return. Use 0 for no limit.
                Strategies should respect this limit for performance.
            any_of_tags_required: Optional list of tags where one of them must be present in the tool's tags
                for it to be considered a match.

        Returns:
            List of Tool objects ranked by relevance, limited to the
            specified count. Empty list if no matches found.

        Raises:
            ValueError: If the query format is invalid for this strategy.
            RuntimeError: If the search operation fails unexpectedly.
        """
        pass

class ToolSearchStrategyConfigSerializer(Serializer[ToolSearchStrategy]):
    """REQUIRED
    Serializer for tool search strategies.

    Defines the contract for serializers that convert tool search strategies to and from
    dictionaries for storage or transmission. Serializers are responsible for:
    - Converting tool search strategies to dictionaries for storage or transmission
    - Converting dictionaries back to tool search strategies
    - Ensuring data consistency during serialization and deserialization
    """
    tool_search_strategy_implementations: Dict[str, Serializer['ToolSearchStrategy']] = {}
    default_strategy = "tag_and_description_word_match"

    def to_dict(self, obj: ToolSearchStrategy) -> dict:
        """REQUIRED
        Convert a tool search strategy to a dictionary.

        Args:
            obj: The tool search strategy to convert.

        Returns:
            The dictionary converted from the tool search strategy.
        """
        return ToolSearchStrategyConfigSerializer.tool_search_strategy_implementations[obj.tool_search_strategy_type].to_dict(obj)

    def validate_dict(self, data: dict) -> ToolSearchStrategy:
        """REQUIRED
        Validate a dictionary and convert it to a tool search strategy.

        Args:
            data: The dictionary to validate and convert.

        Returns:
            The tool search strategy converted from the dictionary.
        """
        try:
            return ToolSearchStrategyConfigSerializer.tool_search_strategy_implementations[data['tool_search_strategy_type']].validate_dict(data)
        except KeyError:
            raise ValueError(f"Invalid tool search strategy type: {data['tool_search_strategy_type']}")
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid ToolSearchStrategy: " + traceback.format_exc()) from e
