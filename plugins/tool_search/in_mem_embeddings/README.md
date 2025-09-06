# UTCP In-Memory Embeddings Search Plugin

This plugin registers the in-memory embedding-based semantic search strategy with UTCP 1.0 via entry points.

## Installation

```bash
pip install utcp-in-mem-embeddings
```

Optionally, for high-quality embeddings:

```bash
pip install utcp-in-mem-embeddings[embedding]
```

Or install the required dependencies directly:

```bash
pip install "sentence-transformers>=2.2.0" "torch>=1.9.0"
```

## Why are sentence-transformers and torch needed?

While the plugin works without these packages (using a simple character frequency-based fallback), installing them provides significant benefits:

- **Enhanced Semantic Understanding**: The `sentence-transformers` package provides pre-trained models that convert text into high-quality vector embeddings, capturing the semantic meaning of text rather than just keywords.

- **Better Search Results**: With these packages installed, the search can understand conceptual similarity between queries and tools, even when they don't share exact keywords.

- **Performance**: The default model (all-MiniLM-L6-v2) offers a good balance between quality and performance for semantic search applications.

- **Fallback Mechanism**: Without these packages, the plugin automatically falls back to a simpler text similarity method, which works but with reduced accuracy.

## How it works

When installed, this package exposes an entry point under `utcp.plugins` so the UTCP core can auto-discover and register the `in_mem_embeddings` strategy.

The embeddings are cached in memory for improved performance during repeated searches.
