from utcp.plugins.discovery import register_tool_search_strategy
from utcp_in_mem_embeddings.in_mem_embeddings_search import InMemEmbeddingsSearchStrategyConfigSerializer


def register():
    """Entry point function to register the in-memory embeddings search strategy."""
    register_tool_search_strategy("in_mem_embeddings", InMemEmbeddingsSearchStrategyConfigSerializer())
