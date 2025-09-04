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

## How it works

When installed, this package exposes an entry point under `utcp.plugins` so the UTCP core can auto-discover and register the `in_mem_embeddings` strategy.

The embeddings are cached in memory for improved performance during repeated searches.
