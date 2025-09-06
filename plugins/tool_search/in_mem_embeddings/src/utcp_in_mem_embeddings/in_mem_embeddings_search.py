"""In-memory embedding-based semantic search strategy for UTCP tools.

This module provides a semantic search implementation that uses sentence embeddings
to find tools based on meaning similarity rather than just keyword matching.
Embeddings are cached in memory for improved performance.
"""

import asyncio
import logging
from typing import List, Tuple, Optional, Literal, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from pydantic import BaseModel, Field

from utcp.interfaces.tool_search_strategy import ToolSearchStrategy
from utcp.data.tool import Tool
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository
from utcp.interfaces.serializer import Serializer

logger = logging.getLogger(__name__)

class InMemEmbeddingsSearchStrategy(ToolSearchStrategy):
    """In-memory semantic search strategy using sentence embeddings.
    
    This strategy converts tool descriptions and search queries into numerical
    embeddings and finds the most semantically similar tools using cosine similarity.
    Embeddings are cached in memory for improved performance during repeated searches.
    """
    
    tool_search_strategy_type: Literal["in_mem_embeddings"] = "in_mem_embeddings"
    
    # Configuration parameters
    model_name: str = Field(
        default="all-MiniLM-L6-v2", 
        description="Sentence transformer model name to use for embeddings. "
                   "Accepts any model from Hugging Face sentence-transformers library. "
                   "Popular options: 'all-MiniLM-L6-v2' (fast, good quality), "
                   "'all-mpnet-base-v2' (slower, higher quality), "
                   "'paraphrase-MiniLM-L6-v2' (paraphrase detection). "
                   "See https://huggingface.co/sentence-transformers for full list."
    )
    similarity_threshold: float = Field(default=0.3, description="Minimum similarity score to consider a match")
    max_workers: int = Field(default=4, description="Maximum number of worker threads for embedding generation")
    cache_embeddings: bool = Field(default=True, description="Whether to cache tool embeddings for performance")
    
    def __init__(self, **data):
        super().__init__(**data)
        self._embedding_model = None
        self._tool_embeddings_cache: Dict[str, np.ndarray] = {}
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self._model_loaded = False
        
    async def _ensure_model_loaded(self):
        """Ensure the embedding model is loaded."""
        if self._model_loaded:
            return
            
        try:
            # Import sentence-transformers here to avoid dependency issues
            from sentence_transformers import SentenceTransformer
            
            # Load the model in a thread to avoid blocking
            loop = asyncio.get_event_loop()
            self._embedding_model = await loop.run_in_executor(
                self._executor, 
                SentenceTransformer, 
                self.model_name
            )
            self._model_loaded = True
            logger.info(f"Loaded embedding model: {self.model_name}")
            
        except ImportError:
            logger.warning("sentence-transformers not available, falling back to simple text similarity")
            self._embedding_model = None
            self._model_loaded = True
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self._embedding_model = None
            self._model_loaded = True

    async def _get_text_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for given text."""
        if not text:
            return np.zeros(384)  # Default dimension for all-MiniLM-L6-v2
            
        if self._embedding_model is None:
            # Fallback to simple text similarity
            return self._simple_text_embedding(text)
            
        try:
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                self._executor,
                self._embedding_model.encode,
                text
            )
            return embedding
        except Exception as e:
            logger.warning(f"Failed to generate embedding for text: {e}")
            return self._simple_text_embedding(text)
    
    def _simple_text_embedding(self, text: str) -> np.ndarray:
        """Simple fallback embedding using character frequency."""
        # Create a simple embedding based on character frequency
        # This is a fallback when sentence-transformers is not available
        embedding = np.zeros(384)
        text_lower = text.lower()
        
        # Simple character frequency-based embedding
        for i, char in enumerate(text_lower):
            if i < 384:
                embedding[i % 384] += ord(char) / 1000.0
                
        # Normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
            
        return embedding
    
    async def _get_tool_embedding(self, tool: Tool) -> np.ndarray:
        """Get or generate embedding for a tool."""
        if not self.cache_embeddings or tool.name not in self._tool_embeddings_cache:
            # Create text representation of the tool
            tool_text = f"{tool.name} {tool.description} {' '.join(tool.tags)}"
            embedding = await self._get_text_embedding(tool_text)
            
            if self.cache_embeddings:
                self._tool_embeddings_cache[tool.name] = embedding
                
            return embedding
        
        return self._tool_embeddings_cache[tool.name]
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        try:
            dot_product = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
                
            return dot_product / (norm_a * norm_b)
        except Exception as e:
            logger.warning(f"Error calculating cosine similarity: {e}")
            return 0.0
    
    async def search_tools(
        self, 
        tool_repository: ConcurrentToolRepository, 
        query: str, 
        limit: int = 10, 
        any_of_tags_required: Optional[List[str]] = None
    ) -> List[Tool]:
        """Search for tools using semantic similarity.
        
        Args:
            tool_repository: The tool repository to search within.
            query: The search query string.
            limit: Maximum number of tools to return.
            any_of_tags_required: Optional list of tags where one of them must be present.
            
        Returns:
            List of Tool objects ranked by semantic similarity.
        """
        if limit < 0:
            raise ValueError("limit must be non-negative")
            
        # Ensure the embedding model is loaded
        await self._ensure_model_loaded()
        
        # Get all tools
        tools: List[Tool] = await tool_repository.get_tools()
        
        # Filter by required tags if specified
        if any_of_tags_required and len(any_of_tags_required) > 0:
            any_of_tags_required = [tag.lower() for tag in any_of_tags_required]
            tools = [
                tool for tool in tools 
                if any(tag.lower() in any_of_tags_required for tag in tool.tags)
            ]
        
        if not tools:
            return []
        
        # Generate query embedding
        query_embedding = await self._get_text_embedding(query)
        
        # Calculate similarity scores for all tools
        tool_scores: List[Tuple[Tool, float]] = []
        
        for tool in tools:
            try:
                tool_embedding = await self._get_tool_embedding(tool)
                similarity = self._cosine_similarity(query_embedding, tool_embedding)
                
                if similarity >= self.similarity_threshold:
                    tool_scores.append((tool, similarity))
                    
            except Exception as e:
                logger.warning(f"Error processing tool {tool.name}: {e}")
                continue
        
        # Sort by similarity score (descending)
        sorted_tools = [
            tool for tool, score in sorted(
                tool_scores, 
                key=lambda x: x[1], 
                reverse=True
            )
        ]
        
        # Return up to 'limit' tools
        return sorted_tools[:limit] if limit > 0 else sorted_tools
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_model_loaded()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._executor:
            self._executor.shutdown(wait=False)


class InMemEmbeddingsSearchStrategyConfigSerializer(Serializer[InMemEmbeddingsSearchStrategy]):
    """Serializer for InMemEmbeddingsSearchStrategy configuration."""
    
    def to_dict(self, obj: InMemEmbeddingsSearchStrategy) -> dict:
        return obj.model_dump()
    
    def validate_dict(self, data: dict) -> InMemEmbeddingsSearchStrategy:
        try:
            return InMemEmbeddingsSearchStrategy.model_validate(data)
        except Exception as e:
            raise ValueError(f"Invalid configuration: {e}") from e
