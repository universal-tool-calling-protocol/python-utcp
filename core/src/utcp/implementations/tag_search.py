"""Tag-based tool search strategy implementation.

This module provides a search strategy that ranks tools based on tag matches
and description keyword matches. It implements a weighted scoring system where
explicit tag matches receive higher scores than description word matches.
"""

from utcp.interfaces.tool_search_strategy import ToolSearchStrategy
from typing import List, Tuple, Optional
from utcp.data.tool import Tool
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository
import re
import asyncio

class TagSearchStrategy(ToolSearchStrategy):
    """Tag-based search strategy for UTCP tools.

    Implements a weighted scoring algorithm that matches search queries against
    tool tags and descriptions. Explicit tag matches receive full weight while
    description word matches receive reduced weight.

    Scoring Algorithm:
        - Exact tag matches: Weight 1.0
        - Tag word matches: Weight equal to description_weight
        - Description word matches: Weight equal to description_weight
        - Only considers description words longer than 2 characters

    Examples:
        >>> strategy = TagSearchStrategy(repository, description_weight=0.3)
        >>> tools = await strategy.search_tools("weather api", limit=5)
        >>> # Returns tools with "weather" or "api" tags/descriptions

    Attributes:
        tool_repository: Repository to search for tools.
        description_weight: Weight multiplier for description matches (0.0-1.0).
    """

    def __init__(self, tool_repository: ConcurrentToolRepository, description_weight: float = 0.3):
        """Initialize the tag search strategy.

        Args:
            tool_repository: Repository containing tools to search.
            description_weight: Weight for description word matches relative to
                tag matches. Should be between 0.0 and 1.0, where 1.0 gives
                equal weight to tags and descriptions.

        Raises:
            ValueError: If description_weight is not between 0.0 and 1.0.
        """
        if not 0.0 <= description_weight <= 1.0:
            raise ValueError("description_weight must be between 0.0 and 1.0")
            
        self.tool_repository = tool_repository
        # Weight for description words vs explicit tags (explicit tags have weight of 1.0)
        self.description_weight = description_weight

    async def search_tools(self, query: str, limit: int = 10, any_of_tags_required: Optional[List[str]] = []) -> List[Tool]:
        """Search tools using tag and description matching.

        Implements a weighted scoring system that ranks tools based on how well
        their tags and descriptions match the search query. Normalizes the query
        and uses word-based matching with configurable weights.

        Scoring Details:
            - Exact tag matches in query: +1.0 points
            - Individual tag words matching query words: +description_weight points
            - Description words matching query words: +description_weight points
            - Only description words > 2 characters are considered

        Args:
            query: Search query string. Case-insensitive, word-based matching.
            limit: Maximum number of tools to return. Must be >= 0.
            any_of_tags_required: Optional list of tags where one of them must be present in the tool's tags
                for it to be considered a match.

        Returns:
            List of Tool objects ranked by relevance score (highest first).
            Empty list if no tools match or repository is empty.

        Raises:
            ValueError: If limit is negative.
        """
        if limit < 0:
            raise ValueError("limit must be non-negative")
        # Normalize query to lowercase and split into words
        query_lower = query.lower()
        # Extract words from the query, filtering out non-word characters
        query_words = set(re.findall(r'\w+', query_lower))
        
        # Get all tools (using asyncio to run the coroutine)
        tools: List[Tool] = await self.tool_repository.get_tools()

        if any_of_tags_required and len(any_of_tags_required) > 0:
            tools = [tool for tool in tools if any(tag in tool.tags for tag in any_of_tags_required)]
        
        # Calculate scores for each tool
        tool_scores: List[Tuple[Tool, float]] = []
        
        for tool in tools:
            score = 0.0
            
            # Score from explicit tags (weight 1.0)
            for tag in tool.tags:
                tag_lower = tag.lower()
                # Check if the tag appears in the query
                if tag_lower in query_lower:
                    score += 1.0
                # Also check if the tag words match query words
                tag_words = set(re.findall(r'\w+', tag_lower))
                for word in tag_words:
                    if word in query_words:
                        score += self.description_weight  # Partial match for tag words
            
            # Score from description (with lower weight)
            if tool.description:
                description_words = set(re.findall(r'\w+', tool.description.lower()))
                for word in description_words:
                    if word in query_words and len(word) > 2:  # Only consider words with length > 2
                        score += self.description_weight
            
            tool_scores.append((tool, score))
        
        # Sort tools by score in descending order
        sorted_tools = [tool for tool, score in sorted(tool_scores, key=lambda x: x[1], reverse=True)]
        
        # Return up to 'limit' tools
        return sorted_tools[:limit]
