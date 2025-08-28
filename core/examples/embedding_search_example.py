#!/usr/bin/env python3
"""
Example demonstrating the embedding search strategy for UTCP tools.

This example shows how to:
1. Create tools with descriptions and tags
2. Use the embedding search strategy to find semantically similar tools
3. Compare results with the traditional tag-based search
"""

import asyncio
import sys
import os

# Add the src directory to the path so we can import utcp modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utcp.data.tool import Tool, JsonSchema
from utcp.data.call_template import CallTemplate
from utcp.implementations.embedding_search import EmbeddingSearchStrategy
from utcp.implementations.tag_search import TagAndDescriptionWordMatchStrategy
from utcp.implementations.in_mem_tool_repository import InMemToolRepository


async def create_sample_tools():
    """Create a collection of sample tools for demonstration."""
    tools = []
    
    # Cooking tools
    tools.append(Tool(
        name="cooking.spatula",
        description="A kitchen utensil used for flipping and turning food while cooking",
        inputs=JsonSchema(),
        outputs=JsonSchema(),
        tags=["cooking", "kitchen", "utensil"],
        tool_call_template=CallTemplate(name="cooking.spatula", description="Spatula tool")
    ))
    
    tools.append(Tool(
        name="cooking.whisk",
        description="A kitchen tool for mixing and aerating ingredients",
        inputs=JsonSchema(),
        outputs=JsonSchema(),
        tags=["cooking", "kitchen", "mixing"],
        tool_call_template=CallTemplate(name="cooking.whisk", description="Whisk tool")
    ))
    
    tools.append(Tool(
        name="cooking.knife",
        description="A sharp blade for cutting and chopping food ingredients",
        inputs=JsonSchema(),
        outputs=JsonSchema(),
        tags=["cooking", "kitchen", "cutting"],
        tool_call_template=CallTemplate(name="cooking.knife", description="Knife tool")
    ))
    
    # Programming tools
    tools.append(Tool(
        name="dev.code_review",
        description="Review and analyze source code for quality and best practices",
        inputs=JsonSchema(),
        outputs=JsonSchema(),
        tags=["programming", "development", "code"],
        tool_call_template=CallTemplate(name="dev.code_review", description="Code review tool")
    ))
    
    tools.append(Tool(
        name="dev.debug",
        description="Find and fix bugs in software code",
        inputs=JsonSchema(),
        outputs=JsonSchema(),
        tags=["programming", "development", "debugging"],
        tool_call_template=CallTemplate(name="dev.debug", description="Debugging tool")
    ))
    
    tools.append(Tool(
        name="dev.test",
        description="Run automated tests to verify code functionality",
        inputs=JsonSchema(),
        outputs=JsonSchema(),
        tags=["programming", "development", "testing"],
        tool_call_template=CallTemplate(name="dev.test", description="Testing tool")
    ))
    
    # Data analysis tools
    tools.append(Tool(
        name="data.analyze",
        description="Analyze datasets and generate insights from data",
        inputs=JsonSchema(),
        outputs=JsonSchema(),
        tags=["data", "analysis", "insights"],
        tool_call_template=CallTemplate(name="data.analyze", description="Data analysis tool")
    ))
    
    tools.append(Tool(
        name="data.visualize",
        description="Create charts and graphs to represent data visually",
        inputs=JsonSchema(),
        outputs=JsonSchema(),
        tags=["data", "visualization", "charts"],
        tool_call_template=CallTemplate(name="data.visualize", description="Data visualization tool")
    ))
    
    tools.append(Tool(
        name="data.clean",
        description="Clean and preprocess raw data for analysis",
        inputs=JsonSchema(),
        outputs=JsonSchema(),
        tags=["data", "cleaning", "preprocessing"],
        tool_call_template=CallTemplate(name="data.clean", description="Data cleaning tool")
    ))
    
    return tools


async def demonstrate_search_strategies():
    """Demonstrate both search strategies with example queries."""
    
    # Create tools and repository
    tools = await create_sample_tools()
    tool_repo = InMemToolRepository()
    
    # Add tools to repository
    for tool in tools:
        await tool_repo.save_tool(tool)
    
    # Create search strategies
    embedding_strategy = EmbeddingSearchStrategy(
        model_name="all-MiniLM-L6-v2",
        similarity_threshold=0.3,
        max_workers=2,
        cache_embeddings=True
    )
    
    tag_strategy = TagAndDescriptionWordMatchStrategy()
    
    # Example queries to test
    test_queries = [
        "I need to cook something",
        "Help me write better code",
        "I have data to analyze",
        "Kitchen equipment",
        "Software development",
        "Data science tasks"
    ]
    
    print("🔍 UTCP Embedding Search Strategy Demo")
    print("=" * 50)
    print()
    
    for query in test_queries:
        print(f"Query: '{query}'")
        print("-" * 30)
        
        # Search with embedding strategy
        print("📊 Embedding Search Results:")
        try:
            embedding_results = await embedding_strategy.search_tools(
                tool_repo, query, limit=3
            )
            for i, tool in enumerate(embedding_results, 1):
                print(f"  {i}. {tool.name} (tags: {', '.join(tool.tags)})")
                print(f"     {tool.description}")
        except Exception as e:
            print(f"  Error: {e}")
        
        print()
        
        # Search with tag strategy
        print("🏷️  Tag-based Search Results:")
        try:
            tag_results = await tag_strategy.search_tools(
                tool_repo, query, limit=3
            )
            for i, tool in enumerate(tag_results, 1):
                print(f"  {i}. {tool.name} (tags: {', '.join(tool.tags)})")
                print(f"     {tool.description}")
        except Exception as e:
            print(f"  Error: {e}")
        
        print("\n" + "=" * 50 + "\n")


async def demonstrate_advanced_features():
    """Demonstrate advanced features of the embedding search strategy."""
    
    print("🚀 Advanced Embedding Search Features")
    print("=" * 50)
    print()
    
    # Create tools and repository
    tools = await create_sample_tools()
    tool_repo = InMemToolRepository()
    
    for tool in tools:
        await tool_repo.save_tool(tool)
    
    # Create strategy with custom configuration
    strategy = EmbeddingSearchStrategy(
        model_name="all-MiniLM-L6-v2",
        similarity_threshold=0.5,  # Higher threshold for more precise matches
        max_workers=4,
        cache_embeddings=True
    )
    
    # Test tag filtering
    print("1. Tag Filtering Example:")
    print("Query: 'cooking tools' with required tags: ['cooking']")
    results = await strategy.search_tools(
        tool_repo, 
        "cooking tools", 
        limit=5,
        any_of_tags_required=["cooking"]
    )
    
    for i, tool in enumerate(results, 1):
        print(f"  {i}. {tool.name} (tags: {', '.join(tool.tags)})")
    
    print()
    
    # Test different similarity thresholds
    print("2. Similarity Threshold Comparison:")
    thresholds = [0.2, 0.4, 0.6, 0.8]
    query = "food preparation"
    
    for threshold in thresholds:
        strategy.similarity_threshold = threshold
        results = await strategy.search_tools(tool_repo, query, limit=5)
        print(f"  Threshold {threshold}: {len(results)} results")
    
    print()
    
    # Test context manager usage
    print("3. Context Manager Usage:")
    async with strategy as ctx_strategy:
        results = await ctx_strategy.search_tools(tool_repo, "software", limit=3)
        print(f"  Found {len(results)} software-related tools")
    
    print("\n" + "=" * 50)


async def main():
    """Main function to run the demonstration."""
    try:
        await demonstrate_search_strategies()
        await demonstrate_advanced_features()
        
        print("✅ Demo completed successfully!")
        print("\n💡 Tips:")
        print("- Install sentence-transformers for better semantic search: pip install sentence-transformers")
        print("- Adjust similarity_threshold based on your needs (0.3-0.7 recommended)")
        print("- Use tag filtering to narrow down results by category")
        print("- The strategy automatically falls back to simple text similarity if sentence-transformers is not available")
        
    except Exception as e:
        print(f"❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
