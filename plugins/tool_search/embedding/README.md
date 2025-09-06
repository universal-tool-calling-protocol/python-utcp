# UTCP Embedding Search Plugin

This plugin registers the embedding-based semantic search strategy with UTCP 1.0 via entry points.

## Installation

```bash
pip install utcp-embedding-search
```

Optionally, for high-quality embeddings:

```bash
pip install "utcp-embedding-search[embedding]"
```

## How it works

When installed, this package exposes an entry point under `utcp.plugins` so the UTCP core can auto-discover and register the `embedding_search` strategy.
