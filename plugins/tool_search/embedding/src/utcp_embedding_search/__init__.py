from utcp.plugins.discovery import register_tool_search_strategy
from utcp.implementations.embedding_search import EmbeddingSearchStrategyConfigSerializer


def register():
    """Entry point function to register the embedding search strategy."""
    register_tool_search_strategy("embedding_search", EmbeddingSearchStrategyConfigSerializer())
