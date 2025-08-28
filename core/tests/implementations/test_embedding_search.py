"""Tests for the EmbeddingSearchStrategy implementation."""

import pytest
import numpy as np
from unittest.mock import patch
from typing import List

from utcp.implementations.embedding_search import EmbeddingSearchStrategy
from utcp.data.tool import Tool, JsonSchema
from utcp.data.call_template import CallTemplate


class MockToolRepository:
    """Simplified mock repository for testing."""

    def __init__(self, tools: List[Tool]):
        self.tools = tools

    async def get_tools(self) -> List[Tool]:
        return self.tools


@pytest.fixture
def sample_tools():
    """Create sample tools for testing."""
    tools = []

    # Tool 1: Cooking related
    tool1 = Tool(
        name="cooking.spatula",
        description="A kitchen utensil used for flipping and turning food while cooking",
        inputs=JsonSchema(),
        outputs=JsonSchema(),
        tags=["cooking", "kitchen", "utensil"],
        tool_call_template=CallTemplate(
            name="cooking.spatula",
            description="Spatula tool",
            call_template_type="default"
        )
    )
    tools.append(tool1)

    # Tool 2: Programming related
    tool2 = Tool(
        name="dev.code_review",
        description="Review and analyze source code for quality and best practices",
        inputs=JsonSchema(),
        outputs=JsonSchema(),
        tags=["programming", "development", "code"],
        tool_call_template=CallTemplate(
            name="dev.code_review",
            description="Code review tool",
            call_template_type="default"
        )
    )
    tools.append(tool2)

    # Tool 3: Data analysis
    tool3 = Tool(
        name="data.analyze",
        description="Analyze datasets and generate insights from data",
        inputs=JsonSchema(),
        outputs=JsonSchema(),
        tags=["data", "analysis", "insights"],
        tool_call_template=CallTemplate(
            name="data.analyze",
            description="Data analysis tool",
            call_template_type="default"
        )
    )
    tools.append(tool3)

    return tools


@pytest.fixture
def embedding_strategy():
    """Create an embedding search strategy instance."""
    return EmbeddingSearchStrategy(
        model_name="all-MiniLM-L6-v2",
        similarity_threshold=0.3,
        max_workers=2,
        cache_embeddings=True
    )


# --- Your existing tests remain unchanged below this line ---


@pytest.mark.asyncio

async def test_embedding_strategy_initialization(embedding_strategy):
    """Test that the embedding strategy initializes correctly."""
    assert embedding_strategy.tool_search_strategy_type == "embedding_search"
    assert embedding_strategy.model_name == "all-MiniLM-L6-v2"
    assert embedding_strategy.similarity_threshold == 0.3
    assert embedding_strategy.max_workers == 2
    assert embedding_strategy.cache_embeddings is True


@pytest.mark.asyncio
async def test_simple_text_embedding_fallback(embedding_strategy):
    """Test the fallback text embedding when sentence-transformers is not available."""
    # Mock the embedding model to be None to trigger fallback
    embedding_strategy._embedding_model = None
    embedding_strategy._model_loaded = True
    
    text = "test text"
    embedding = await embedding_strategy._get_text_embedding(text)
    
    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (384,)
    assert np.linalg.norm(embedding) > 0


@pytest.mark.asyncio
async def test_cosine_similarity_calculation(embedding_strategy):
    """Test cosine similarity calculation."""
    # Test with identical vectors
    vec1 = np.array([1.0, 0.0, 0.0])
    vec2 = np.array([1.0, 0.0, 0.0])
    similarity = embedding_strategy._cosine_similarity(vec1, vec2)
    assert similarity == pytest.approx(1.0)
    
    # Test with orthogonal vectors
    vec3 = np.array([0.0, 1.0, 0.0])
    similarity = embedding_strategy._cosine_similarity(vec1, vec3)
    assert similarity == pytest.approx(0.0)
    
    # Test with zero vectors
    vec4 = np.zeros(3)
    similarity = embedding_strategy._cosine_similarity(vec1, vec4)
    assert similarity == 0.0


@pytest.mark.asyncio
async def test_tool_embedding_generation(embedding_strategy, sample_tools):
    """Test that tool embeddings are generated and cached correctly."""
    tool = sample_tools[0]
    
    # Mock the text embedding method
    with patch.object(embedding_strategy, '_get_text_embedding') as mock_embed:
        mock_embed.return_value = np.random.rand(384)
        
        # First call should generate and cache
        embedding1 = await embedding_strategy._get_tool_embedding(tool)
        assert tool.name in embedding_strategy._tool_embeddings_cache
        
        # Second call should use cache
        embedding2 = await embedding_strategy._get_tool_embedding(tool)
        assert np.array_equal(embedding1, embedding2)
        
        # Verify the mock was called only once
        mock_embed.assert_called_once()


@pytest.mark.asyncio
async def test_search_tools_basic(embedding_strategy, sample_tools):
    """Test basic search functionality."""
    tool_repo = MockToolRepository(sample_tools)
    
    # Mock the embedding methods
    with patch.object(embedding_strategy, '_get_text_embedding') as mock_query_embed, \
         patch.object(embedding_strategy, '_get_tool_embedding') as mock_tool_embed:
        
        # Create mock embeddings
        query_embedding = np.random.rand(384)
        tool_embeddings = [np.random.rand(384) for _ in sample_tools]
        
        mock_query_embed.return_value = query_embedding
        mock_tool_embed.side_effect = tool_embeddings
        
        # Mock cosine similarity to return high scores
        with patch.object(embedding_strategy, '_cosine_similarity') as mock_sim:
            mock_sim.return_value = 0.8  # High similarity
            
            results = await embedding_strategy.search_tools(tool_repo, "cooking", limit=2)
            
            assert len(results) == 2
            assert all(isinstance(tool, Tool) for tool in results)


@pytest.mark.asyncio
async def test_search_tools_with_tag_filtering(embedding_strategy, sample_tools):
    """Test search with tag filtering."""
    tool_repo = MockToolRepository(sample_tools)
    
    with patch.object(embedding_strategy, '_get_text_embedding') as mock_query_embed, \
         patch.object(embedding_strategy, '_get_tool_embedding') as mock_tool_embed, \
         patch.object(embedding_strategy, '_cosine_similarity') as mock_sim:
        
        mock_query_embed.return_value = np.random.rand(384)
        mock_tool_embed.return_value = np.random.rand(384)
        mock_sim.return_value = 0.8
        
        # Search with required tags
        results = await embedding_strategy.search_tools(
            tool_repo, 
            "cooking", 
            limit=10,
            any_of_tags_required=["cooking", "kitchen"]
        )
        
        # Should only return tools with cooking or kitchen tags
        assert all(
            any(tag in ["cooking", "kitchen"] for tag in tool.tags)
            for tool in results
        )


@pytest.mark.asyncio
async def test_search_tools_with_similarity_threshold(embedding_strategy, sample_tools):
    """Test that similarity threshold filtering works correctly."""
    tool_repo = MockToolRepository(sample_tools)
    
    with patch.object(embedding_strategy, '_get_text_embedding') as mock_query_embed, \
         patch.object(embedding_strategy, '_get_tool_embedding') as mock_tool_embed, \
         patch.object(embedding_strategy, '_cosine_similarity') as mock_sim:
        
        mock_query_embed.return_value = np.random.rand(384)
        mock_tool_embed.return_value = np.random.rand(384)
        
        # Set threshold to 0.5 and return scores below and above
        embedding_strategy.similarity_threshold = 0.5
        mock_sim.side_effect = [0.3, 0.7, 0.2]  # Only second tool should pass
        
        results = await embedding_strategy.search_tools(tool_repo, "test", limit=10)
        
        assert len(results) == 1  # Only one tool above threshold


@pytest.mark.asyncio
async def test_search_tools_limit_respected(embedding_strategy, sample_tools):
    """Test that the limit parameter is respected."""
    tool_repo = MockToolRepository(sample_tools)
    
    with patch.object(embedding_strategy, '_get_text_embedding') as mock_query_embed, \
         patch.object(embedding_strategy, '_get_tool_embedding') as mock_tool_embed, \
         patch.object(embedding_strategy, '_cosine_similarity') as mock_sim:
        
        mock_query_embed.return_value = np.random.rand(384)
        mock_tool_embed.return_value = np.random.rand(384)
        mock_sim.return_value = 0.8
        
        # Test with limit 1
        results = await embedding_strategy.search_tools(tool_repo, "test", limit=1)
        assert len(results) == 1
        
        # Test with limit 0 (no limit)
        results = await embedding_strategy.search_tools(tool_repo, "test", limit=0)
        assert len(results) == 3  # All tools


@pytest.mark.asyncio
async def test_search_tools_empty_repository(embedding_strategy):
    """Test search behavior with empty tool repository."""
    tool_repo = MockToolRepository([])
    
    results = await embedding_strategy.search_tools(tool_repo, "test", limit=10)
    assert results == []


@pytest.mark.asyncio
async def test_search_tools_invalid_limit(embedding_strategy, sample_tools):
    """Test that invalid limit values raise appropriate errors."""
    tool_repo = MockToolRepository(sample_tools)
    
    with pytest.raises(ValueError, match="limit must be non-negative"):
        await embedding_strategy.search_tools(tool_repo, "test", limit=-1)


@pytest.mark.asyncio
async def test_context_manager_behavior(embedding_strategy):
    """Test async context manager behavior."""
    async with embedding_strategy as strategy:
        assert strategy._model_loaded is True
    
    # Executor should be shut down
    assert strategy._executor._shutdown is True


@pytest.mark.asyncio
async def test_error_handling_in_search(embedding_strategy, sample_tools):
    """Test that errors in search are handled gracefully."""
    tool_repo = MockToolRepository(sample_tools)
    
    with patch.object(embedding_strategy, '_get_text_embedding') as mock_query_embed, \
         patch.object(embedding_strategy, '_get_tool_embedding') as mock_tool_embed:
        
        mock_query_embed.return_value = np.random.rand(384)
        
        # Make the second tool fail
        def mock_tool_embed_side_effect(tool):
            if tool.name == "dev.code_review":
                raise Exception("Simulated error")
            return np.random.rand(384)
        
        mock_tool_embed.side_effect = mock_tool_embed_side_effect
        
        # Mock cosine similarity
        with patch.object(embedding_strategy, '_cosine_similarity') as mock_sim:
            mock_sim.return_value = 0.8
            
            # Should not crash, just skip the problematic tool
            results = await embedding_strategy.search_tools(tool_repo, "test", limit=10)
            
            # Should return tools that didn't fail
            assert len(results) == 2  # One tool failed, so only 2 results


@pytest.mark.asyncio
async def test_embedding_strategy_config_serializer():
    """Test the configuration serializer."""
    from utcp.implementations.embedding_search import EmbeddingSearchStrategyConfigSerializer
    
    serializer = EmbeddingSearchStrategyConfigSerializer()
    
    # Test serialization
    strategy = EmbeddingSearchStrategy(
        model_name="test-model",
        similarity_threshold=0.5,
        max_workers=8,
        cache_embeddings=False
    )
    
    config_dict = serializer.to_dict(strategy)
    assert config_dict["model_name"] == "test-model"
    assert config_dict["similarity_threshold"] == 0.5
    assert config_dict["max_workers"] == 8
    assert config_dict["cache_embeddings"] is False
    
    # Test deserialization
    restored_strategy = serializer.validate_dict(config_dict)
    assert restored_strategy.model_name == "test-model"
    assert restored_strategy.similarity_threshold == 0.5
    assert restored_strategy.max_workers == 8
    assert restored_strategy.cache_embeddings is False
