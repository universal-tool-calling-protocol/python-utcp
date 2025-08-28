# UTCP Embedding Search Plugin

This document describes the new embedding-based semantic search strategy for UTCP tools, which provides intelligent tool discovery based on meaning similarity rather than just keyword matching.

## Overview

The `EmbeddingSearchStrategy` is a plugin that implements semantic search for UTCP tools using sentence embeddings. It converts tool descriptions and search queries into numerical vectors and finds the most semantically similar tools using cosine similarity.

## Features

- **Semantic Understanding**: Finds tools based on meaning, not just exact keyword matches
- **Configurable Similarity Threshold**: Adjustable threshold for result quality
- **Automatic Fallback**: Falls back to simple text similarity if sentence-transformers is unavailable
- **Embedding Caching**: Caches tool embeddings for improved performance
- **Tag Filtering**: Supports filtering results by required tags
- **Async Support**: Fully asynchronous implementation for non-blocking operations
- **Context Manager**: Proper resource management with async context manager

## Installation

### Basic Installation

The core functionality is available with the basic dependencies:

```bash
pip install utcp
```

### Enhanced Semantic Search

For the best semantic search experience, install the optional embedding dependencies:

```bash
pip install utcp[embedding]
```

This installs:
- `sentence-transformers>=2.2.0` - For high-quality sentence embeddings
- `torch>=1.9.0` - PyTorch backend for sentence-transformers

## Quick Start

### Basic Usage

```python
import asyncio
from utcp.implementations.embedding_search import EmbeddingSearchStrategy
from utcp.implementations.in_mem_tool_repository import InMemToolRepository

async def main():
    # Create a tool repository with some tools
    tool_repo = InMemToolRepository()
    # ... add tools to repository ...
    
    # Create the embedding search strategy
    strategy = EmbeddingSearchStrategy(
        model_name="all-MiniLM-L6-v2",
        similarity_threshold=0.3,
        max_workers=4,
        cache_embeddings=True
    )
    
    # Search for tools
    results = await strategy.search_tools(
        tool_repo, 
        "I need to process some data", 
        limit=5
    )
    
    for tool in results:
        print(f"Found: {tool.name} - {tool.description}")

asyncio.run(main())
```

### Using as a Context Manager

```python
async with EmbeddingSearchStrategy() as strategy:
    results = await strategy.search_tools(tool_repo, "cooking tools", limit=3)
    # Strategy automatically manages resources
```

## Configuration Options

### EmbeddingSearchStrategy Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | str | "all-MiniLM-L6-v2" | Sentence transformer model to use |
| `similarity_threshold` | float | 0.3 | Minimum similarity score (0.0-1.0) |
| `max_workers` | int | 4 | Maximum worker threads for embedding generation |
| `cache_embeddings` | bool | True | Whether to cache tool embeddings |

### Recommended Similarity Thresholds

- **0.2-0.3**: Broad matches, more results
- **0.4-0.5**: Balanced precision and recall
- **0.6-0.7**: High precision, fewer results
- **0.8+**: Very high precision, may miss relevant tools

## How It Works

### 1. Text to Embedding Conversion

The strategy converts text into numerical embeddings:

```python
# Query: "I need to analyze data"
# Gets converted to: [0.1, -0.3, 0.8, ...] (384-dimensional vector)

# Tool description: "Analyze datasets and generate insights"
# Gets converted to: [0.2, -0.1, 0.9, ...] (384-dimensional vector)
```

### 2. Similarity Calculation

Uses cosine similarity to measure how similar two embeddings are:

```python
similarity = dot_product(embedding1, embedding2) / (norm(embedding1) * norm(embedding2))
```

### 3. Result Ranking

Tools are ranked by similarity score and filtered by the threshold.

## Advanced Usage

### Tag Filtering

```python
# Only return tools with specific tags
results = await strategy.search_tools(
    tool_repo,
    "data processing",
    limit=5,
    any_of_tags_required=["data", "analysis"]
)
```

### Custom Model Selection

```python
# Use a different sentence transformer model
strategy = EmbeddingSearchStrategy(
    model_name="paraphrase-multilingual-MiniLM-L12-v2",  # Multilingual support
    similarity_threshold=0.4
)
```

### Performance Tuning

```python
# Optimize for your use case
strategy = EmbeddingSearchStrategy(
    max_workers=8,  # More workers for faster processing
    cache_embeddings=True,  # Cache for repeated searches
    similarity_threshold=0.5  # Higher threshold for quality
)
```

## Fallback Behavior

If `sentence-transformers` is not available, the strategy automatically falls back to a simple text similarity approach:

- Uses character frequency-based embeddings
- Maintains the same API
- Provides reasonable results for basic use cases

## Integration with UTCP

The embedding search strategy integrates seamlessly with the UTCP plugin system:

```python
# The strategy is automatically registered when the module is imported
from utcp.implementations.embedding_search import EmbeddingSearchStrategy

# Use it in your UTCP client configuration
config = UtcpClientConfig(
    tool_search_strategy=EmbeddingSearchStrategy(
        similarity_threshold=0.4
    )
)
```

## Performance Considerations

### Memory Usage

- Each tool embedding uses ~1.5KB of memory (384 dimensions × 4 bytes)
- With caching enabled, memory usage grows with the number of tools
- Consider disabling caching for very large tool repositories

### Processing Speed

- First search: Slower due to model loading and embedding generation
- Subsequent searches: Faster due to caching
- More workers = faster embedding generation but higher memory usage

### Model Loading

- Models are downloaded on first use (~80MB for all-MiniLM-L6-v2)
- Consider pre-downloading models in production environments

## Troubleshooting

### Common Issues

1. **Import Error for sentence-transformers**
   - Install with: `pip install sentence-transformers`
   - The strategy will fall back to simple text similarity

2. **Slow First Search**
   - This is normal - the model needs to load
   - Subsequent searches will be faster

3. **Memory Issues**
   - Reduce `max_workers`
   - Disable `cache_embeddings`
   - Use a smaller model (e.g., "all-MiniLM-L6-v2" instead of larger models)

4. **Low Quality Results**
   - Adjust `similarity_threshold`
   - Ensure tool descriptions are detailed and meaningful
   - Consider using more specific queries

### Debug Mode

Enable debug logging to see what's happening:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# The strategy will log detailed information about:
# - Model loading
# - Embedding generation
# - Similarity calculations
# - Search results
```

## Examples

See `core/examples/embedding_search_example.py` for comprehensive examples demonstrating:

- Basic search functionality
- Tag filtering
- Similarity threshold adjustment
- Context manager usage
- Comparison with tag-based search

## Contributing

To contribute to the embedding search plugin:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

This plugin is part of the UTCP project and follows the same license terms.

## Support

For issues and questions:

1. Check the troubleshooting section above
2. Review the example code
3. Open an issue on the GitHub repository
4. Check the UTCP documentation

---

**Note**: The embedding search plugin requires Python 3.10+ and is designed to work seamlessly with the existing UTCP ecosystem while providing enhanced semantic search capabilities.
