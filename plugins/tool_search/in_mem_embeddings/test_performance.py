#!/usr/bin/env python3
"""Performance test for the in-memory embeddings plugin."""

import sys
import asyncio
import time
from pathlib import Path

# Add paths
plugin_src = Path(__file__).parent / "src"
core_src = Path(__file__).parent.parent.parent.parent / "core" / "src"
sys.path.insert(0, str(plugin_src))
sys.path.insert(0, str(core_src))

async def test_performance():
    """Test plugin performance with multiple tools and searches."""
    print("⚡ Testing Performance...")
    
    try:
        from utcp_in_mem_embeddings.in_mem_embeddings_search import InMemEmbeddingsSearchStrategy
        from utcp.data.tool import Tool, JsonSchema
        from utcp.data.call_template import CallTemplate
        
        # Create strategy
        strategy = InMemEmbeddingsSearchStrategy(
            model_name="all-MiniLM-L6-v2",
            similarity_threshold=0.3,
            max_workers=2,
            cache_embeddings=True
        )
        
        # Create many tools
        print("1. Creating 100 test tools...")
        tools = []
        for i in range(100):
            tool = Tool(
                name=f"test_tool{i}",
                description=f"Test tool {i} for various purposes like cooking, coding, data analysis",
                inputs=JsonSchema(),
                outputs=JsonSchema(),
                tags=["test", f"category{i%5}"],
                tool_call_template=CallTemplate(
                    name=f"test_tool{i}",
                    description=f"Test tool {i}",
                    call_template_type="default"
                )
            )
            tools.append(tool)
        
        # Mock repository
        class MockRepo:
            def __init__(self, tools):
                self.tools = tools
            async def get_tools(self):
                return self.tools
        
        repo = MockRepo(tools)
        
        # Test 1: First search (cold start)
        print("2. Testing cold start performance...")
        start_time = time.perf_counter()
        results1 = await strategy.search_tools(repo, "cooking tools", limit=10)
        cold_time = time.perf_counter() - start_time
        print(f"   ⏱️  Cold start: {cold_time:.3f}s, found {len(results1)} results")
        
        # Test 2: Second search (warm cache)
        print("3. Testing warm cache performance...")
        start_time = time.perf_counter()
        results2 = await strategy.search_tools(repo, "coding tools", limit=10)
        warm_time = time.perf_counter() - start_time
        print(f"   ⏱️  Warm cache: {warm_time:.3f}s, found {len(results2)} results")
        
        # Test 3: Multiple searches
        print("4. Testing multiple searches...")
        queries = ["cooking", "programming", "data analysis", "testing", "utilities"]
        start_time = time.perf_counter()
        
        for query in queries:
            await strategy.search_tools(repo, query, limit=5)
        
        total_time = time.perf_counter() - start_time
        avg_time = total_time / len(queries)
        print(f"   ⏱️  Average per search: {avg_time:.3f}s")
        
        # Performance assertions
        assert cold_time < 10.0, f"Cold start too slow: {cold_time}s"  # Allow more time for model loading
        assert warm_time < 1.0, f"Warm cache too slow: {warm_time}s"
        assert avg_time < 0.5, f"Average search too slow: {avg_time}s"
        
        print("\n🎉 Performance test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_performance())
    sys.exit(0 if success else 1)
