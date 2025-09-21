#!/usr/bin/env python3
"""Integration tests to verify the plugin works with the core UTCP system."""

import sys
from pathlib import Path
import pytest
import pytest_asyncio

# Add paths
plugin_src = (Path(__file__).parent / "src").resolve()
core_src = (Path(__file__).parent.parent.parent.parent / "core" / "src").resolve()
sys.path.insert(0, str(plugin_src))
sys.path.insert(0, str(core_src))


@pytest.fixture(scope="session")
def register_plugin():
    """Register the plugin once for all tests."""
    from utcp_in_mem_embeddings import register
    register()
    return True


@pytest_asyncio.fixture
async def sample_tools():
    """Create sample tools for testing."""
    from utcp.data.tool import Tool, JsonSchema
    from utcp.data.call_template import CallTemplate
    
    return [
        Tool(
            name="test.tool1",
            description="A test tool for cooking",
            inputs=JsonSchema(),
            outputs=JsonSchema(),
            tags=["cooking", "test"],
            tool_call_template=CallTemplate(
                name="test.tool1",
                call_template_type="default"
            )
        ),
        Tool(
            name="test.tool2",
            description="A test tool for programming",
            inputs=JsonSchema(),
            outputs=JsonSchema(),
            tags=["programming", "development"],
            tool_call_template=CallTemplate(
                name="test.tool2",
                call_template_type="default"
            )
        )
    ]


@pytest_asyncio.fixture
async def tool_repository(sample_tools):
    """Create a tool repository with sample tools."""
    from utcp.implementations.in_mem_tool_repository import InMemToolRepository
    from utcp.data.utcp_manual import UtcpManual
    from utcp.data.call_template import CallTemplate
    
    repo = InMemToolRepository()
    manual = UtcpManual(tools=sample_tools)
    manual_call_template = CallTemplate(name="test_manual", call_template_type="default")
    await repo.save_manual(manual_call_template, manual)
    
    return repo


@pytest.mark.asyncio
async def test_plugin_registration(register_plugin):
    """Test that the plugin can be registered successfully."""
    # The fixture already registers the plugin, so we just verify it worked
    assert register_plugin is True


@pytest.mark.asyncio
async def test_plugin_discovery(register_plugin):
    """Test that the core system can discover the registered plugin."""
    from utcp.interfaces.tool_search_strategy import ToolSearchStrategyConfigSerializer
    
    strategies = ToolSearchStrategyConfigSerializer.tool_search_strategy_implementations
    assert "in_mem_embeddings" in strategies, "Plugin should be discoverable by core system"


@pytest.mark.asyncio
async def test_strategy_creation_through_core(register_plugin):
    """Test creating strategy instance through the core serialization system."""
    from utcp.interfaces.tool_search_strategy import ToolSearchStrategyConfigSerializer
    
    serializer = ToolSearchStrategyConfigSerializer()
    
    strategy_config = {
        "tool_search_strategy_type": "in_mem_embeddings",
        "model_name": "all-MiniLM-L6-v2",
        "similarity_threshold": 0.3
    }
    
    strategy = serializer.validate_dict(strategy_config)
    assert strategy.tool_search_strategy_type == "in_mem_embeddings"
    assert strategy.model_name == "all-MiniLM-L6-v2"
    assert strategy.similarity_threshold == 0.3


@pytest.mark.asyncio
async def test_basic_search_functionality(register_plugin, tool_repository):
    """Test basic search functionality with the plugin."""
    from utcp.interfaces.tool_search_strategy import ToolSearchStrategyConfigSerializer
    
    # Create strategy through core system
    serializer = ToolSearchStrategyConfigSerializer()
    strategy_config = {
        "tool_search_strategy_type": "in_mem_embeddings",
        "model_name": "all-MiniLM-L6-v2",
        "similarity_threshold": 0.3
    }
    strategy = serializer.validate_dict(strategy_config)
    
    # Test search for cooking-related tools
    results = await strategy.search_tools(tool_repository, "cooking", limit=1)
    assert len(results) > 0, "Search should return at least one result for 'cooking' query"
    
    # Verify the result is relevant
    cooking_tool = results[0]
    assert "cooking" in cooking_tool.description.lower() or "cooking" in cooking_tool.tags


@pytest.mark.asyncio
async def test_search_with_different_queries(register_plugin, tool_repository):
    """Test search functionality with different query types."""
    from utcp.interfaces.tool_search_strategy import ToolSearchStrategyConfigSerializer
    
    serializer = ToolSearchStrategyConfigSerializer()
    strategy_config = {
        "tool_search_strategy_type": "in_mem_embeddings",
        "model_name": "all-MiniLM-L6-v2",
        "similarity_threshold": 0.3
    }
    strategy = serializer.validate_dict(strategy_config)
    
    # Test different queries
    test_cases = [
        ("cooking", "cooking"),
        ("programming", "programming"),
        ("development", "programming")  # Should match programming tool
    ]
    
    for query, expected_tag in test_cases:
        results = await strategy.search_tools(tool_repository, query, limit=2)
        assert len(results) > 0, f"Search should return results for '{query}' query"
        
        # Check if any result contains the expected tag
        found_relevant = any(
            expected_tag in tool.tags or expected_tag in tool.description.lower()
            for tool in results
        )
        assert found_relevant, f"Results should be relevant to '{query}' query"


@pytest.mark.asyncio
async def test_search_limit_parameter(register_plugin, tool_repository):
    """Test that the limit parameter works correctly."""
    from utcp.interfaces.tool_search_strategy import ToolSearchStrategyConfigSerializer
    
    serializer = ToolSearchStrategyConfigSerializer()
    strategy_config = {
        "tool_search_strategy_type": "in_mem_embeddings",
        "model_name": "all-MiniLM-L6-v2",
        "similarity_threshold": 0.1  # Lower threshold to get more results
    }
    strategy = serializer.validate_dict(strategy_config)
    
    # Test with limit=1
    results_1 = await strategy.search_tools(tool_repository, "test", limit=1)
    assert len(results_1) <= 1, "Should respect limit=1"
    
    # Test with limit=2
    results_2 = await strategy.search_tools(tool_repository, "test", limit=2)
    assert len(results_2) <= 2, "Should respect limit=2"


@pytest.mark.asyncio
async def test_similarity_threshold(register_plugin, tool_repository):
    """Test that similarity threshold affects results."""
    from utcp.interfaces.tool_search_strategy import ToolSearchStrategyConfigSerializer
    
    serializer = ToolSearchStrategyConfigSerializer()
    
    # Test with high threshold (should return fewer results)
    high_threshold_config = {
        "tool_search_strategy_type": "in_mem_embeddings",
        "model_name": "all-MiniLM-L6-v2",
        "similarity_threshold": 0.9
    }
    high_threshold_strategy = serializer.validate_dict(high_threshold_config)
    
    # Test with low threshold (should return more results)
    low_threshold_config = {
        "tool_search_strategy_type": "in_mem_embeddings",
        "model_name": "all-MiniLM-L6-v2",
        "similarity_threshold": 0.1
    }
    low_threshold_strategy = serializer.validate_dict(low_threshold_config)
    
    # Search with both strategies
    high_results = await high_threshold_strategy.search_tools(tool_repository, "random_query", limit=10)
    low_results = await low_threshold_strategy.search_tools(tool_repository, "random_query", limit=10)
    
    # Low threshold should return same or more results than high threshold
    assert len(low_results) >= len(high_results), "Lower threshold should return more results"
