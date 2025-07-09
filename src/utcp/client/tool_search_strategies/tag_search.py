from utcp.client.tool_search_strategy import ToolSearchStrategy
from typing import List, Dict, Tuple
from utcp.shared.tool import Tool
from utcp.client.tool_repository import ToolRepository
import re
import asyncio

class TagSearchStrategy(ToolSearchStrategy):

    def __init__(self, tool_repository: ToolRepository, description_weight: float = 0.3):
        self.tool_repository = tool_repository
        # Weight for description words vs explicit tags (explicit tags have weight of 1.0)
        self.description_weight = description_weight

    async def search_tools(self, query: str, limit: int = 10) -> List[Tool]:
        """
        Return tools ordered by tag occurrences in the query.
        
        Uses both explicit tags and words from tool descriptions (with less weight).
        
        Args:
            query: The search query string
            limit: Maximum number of tools to return
            
        Returns:
            List of tools ordered by relevance to the query
        """
        # Normalize query to lowercase and split into words
        query_lower = query.lower()
        # Extract words from the query, filtering out non-word characters
        query_words = set(re.findall(r'\w+', query_lower))
        
        # Get all tools (using asyncio to run the coroutine)
        tools = await self.tool_repository.get_tools()
        
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
