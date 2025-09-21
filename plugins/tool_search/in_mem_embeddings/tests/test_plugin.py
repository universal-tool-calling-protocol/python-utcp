#!/usr/bin/env python3
"""Simple test script to verify the in-memory embeddings plugin works."""

import sys
import os
import asyncio
from pathlib import Path
import pytest

# Add the plugin source to Python path
plugin_src = Path(__file__).parent / "src"
sys.path.insert(0, str(plugin_src))

# Add core to path for imports
core_src = Path(__file__).parent.parent.parent.parent / "core" / "src"
sys.path.insert(0, str(core_src))

@pytest.mark.asyncio
async def test_plugin():
    """Test the plugin functionality."""
    print("🧪 Testing In-Memory Embeddings Plugin...")
    
    try:
        # Test 1: Import the plugin
        print("1. Testing imports...")
        from utcp_in_mem_embeddings.in_mem_embeddings_search import InMemEmbeddingsSearchStrategy
        from utcp_in_mem_embeddings import register
        print("   ✅ Imports successful")
        
        # Test 2: Create strategy instance
        print("2. Testing strategy creation...")
        strategy = InMemEmbeddingsSearchStrategy(
            model_name="all-MiniLM-L6-v2",
            similarity_threshold=0.3,
            max_workers=2,
            cache_embeddings=True
        )
        print(f"   ✅ Strategy created: {strategy.tool_search_strategy_type}")
        
        # Test 3: Test registration function
        print("3. Testing registration...")
        register()
        print("   ✅ Registration function works")
        
        # Test 4: Test basic functionality
        print("4. Testing basic functionality...")
        
        # Create mock tools
        from utcp.data.tool import Tool, JsonSchema
        from utcp.data.call_template import CallTemplate
        
        tools = [
            Tool(
                name="cooking.spatula",
                description="A kitchen utensil for flipping food",
                inputs=JsonSchema(),
                outputs=JsonSchema(),
                tags=["cooking", "kitchen"],
                tool_call_template=CallTemplate(
                    name="cooking.spatula",
                    description="Spatula tool",
                    call_template_type="default"
                )
            ),
            Tool(
                name="dev.code_review",
                description="Review source code for quality",
                inputs=JsonSchema(),
                outputs=JsonSchema(),
                tags=["programming", "development"],
                tool_call_template=CallTemplate(
                    name="dev.code_review",
                    description="Code review tool",
                    call_template_type="default"
                )
            )
        ]
        
        # Create mock repository
        class MockRepo:
            def __init__(self, tools):
                self.tools = tools

            async def get_tools(self):
                return self.tools
        
        repo = MockRepo(tools)
        
        # Test search
        results = await strategy.search_tools(repo, "cooking utensils", limit=2)
        print(f"   ✅ Search completed, found {len(results)} results")
        
        if results:
            print(f"   📋 Top result: {results[0].name}")
        
        print("\n🎉 All tests passed! Plugin is working correctly.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        assert False, f"Plugin test failed: {e}"
