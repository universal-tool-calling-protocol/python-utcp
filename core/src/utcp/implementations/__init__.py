from utcp.implementations.in_mem_tool_repository import InMemToolRepository
from utcp.implementations.tag_search import TagSearchStrategy
from utcp.discovery import register_tool_repository, register_tool_search_strategy
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository
from utcp.interfaces.tool_search_strategy import ToolSearchStrategy

register_tool_repository(ConcurrentToolRepository.default_repository, InMemToolRepository())
register_tool_search_strategy(ToolSearchStrategy.default_strategy, TagSearchStrategy())

__all__ = [
    "InMemToolRepository",
    "TagSearchStrategy",
]
