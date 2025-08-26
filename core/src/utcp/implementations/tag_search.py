from utcp.interfaces.tool_search_strategy import ToolSearchStrategy
from typing import List, Tuple, Optional, Literal
from utcp.data.tool import Tool
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository
import re
from utcp.interfaces.serializer import Serializer

class TagAndDescriptionWordMatchStrategy(ToolSearchStrategy):
    """REQUIRED
    Tag and description word match strategy.

    This strategy matches tools based on the presence of tags and words in the description.
    """
    tool_search_strategy_type: Literal["tag_and_description_word_match"] = "tag_and_description_word_match"
    description_weight: float = 1
    tag_weight: float = 3

    async def search_tools(self, tool_repository: ConcurrentToolRepository, query: str, limit: int = 10, any_of_tags_required: Optional[List[str]] = None) -> List[Tool]:
        """REQUIRED
        Search for tools based on the given query.

        Args:
            tool_repository: The tool repository to search in.
            query: The query to search for.
            limit: The maximum number of results to return.
            any_of_tags_required: A list of tags that must be present in the tool.

        Returns:
            A list of tools that match the query.
        """
        if limit < 0:
            raise ValueError("limit must be non-negative")
        # Normalize query to lowercase and split into words
        query_lower = query.lower()
        # Extract words from the query, filtering out non-word characters
        query_words = set(re.findall(r'\w+', query_lower))
        
        # Get all tools
        tools: List[Tool] = await tool_repository.get_tools()

        if any_of_tags_required is not None and len(any_of_tags_required) > 0:
            any_of_tags_required = [tag.lower() for tag in any_of_tags_required]
            tools = [tool for tool in tools if any(tag.lower() in any_of_tags_required for tag in tool.tags)]
        
        # Calculate scores for each tool
        tool_scores: List[Tuple[Tool, float]] = []
        
        for tool in tools:
            score = 0.0
            
            # Score from explicit tags (weight 1.0)
            for tag in tool.tags:
                tag_lower = tag.lower()
                # Check if the tag appears in the query
                if tag_lower in query_lower:
                    score += self.tag_weight
                    continue
                # Also check if the tag words match query words
                tag_words = set(re.findall(r'\w+', tag_lower))
                for word in tag_words:
                    if word in query_words:
                        score += self.tag_weight
                        break
            
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

class TagAndDescriptionWordMatchStrategyConfigSerializer(Serializer[TagAndDescriptionWordMatchStrategy]):
    """REQUIRED
    Serializer for `TagAndDescriptionWordMatchStrategy`.

    Converts a `TagAndDescriptionWordMatchStrategy` instance to a dictionary and vice versa.
    """
    def to_dict(self, obj: TagAndDescriptionWordMatchStrategy) -> dict:
        """REQUIRED
        Convert a `TagAndDescriptionWordMatchStrategy` instance to a dictionary.

        Args:
            obj: The `TagAndDescriptionWordMatchStrategy` instance to convert.

        Returns:
            A dictionary representing the `TagAndDescriptionWordMatchStrategy` instance.
        """
        return obj.model_dump()

    def validate_dict(self, data: dict) -> TagAndDescriptionWordMatchStrategy:
        """REQUIRED
        Convert a dictionary to a `TagAndDescriptionWordMatchStrategy` instance.

        Args:
            data: The dictionary to convert.

        Returns:
            A `TagAndDescriptionWordMatchStrategy` instance representing the dictionary.
        """
        try:
            return TagAndDescriptionWordMatchStrategy.model_validate(data)
        except Exception as e:
            raise ValueError(f"Invalid configuration: {e}") from e
