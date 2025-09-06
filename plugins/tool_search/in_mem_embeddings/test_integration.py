#!/usr/bin/env python3
"""Integration test to verify the plugin works with the core UTCP system."""

import sys
import asyncio
from pathlib import Path

# Add paths
plugin_src = Path(__file__).parent / "src"
core_src = Path(__file__).parent.parent.parent.parent / "core" / "src"
sys.path.insert(0, str(plugin_src))
sys.path.insert(0, str(core_src))

async def test_integration():
    """Test plugin integration with core system."""
    print("🔗 Testing Integration with Core UTCP System...")
    
    try:
        # Test 1: Plugin registration
        print("1. Testing plugin registration...")
        from utcp_in_mem_embeddings import register
        register()
        print("   ✅ Plugin registered successfully")
        
        # Test 2: Core system can discover the plugin
        print("2. Testing plugin discovery...")
        from utcp.interfaces.tool_search_strategy import ToolSearchStrategyConfigSerializer
        strategies = ToolSearchStrategyConfigSerializer.tool_search_strategy_implementations
        assert "in_mem_embeddings" in strategies
        print("   ✅ Plugin discovered by core system")
        
        # Test 3: Create strategy through core system
        print("3. Testing strategy creation through core...")
        from utcp.interfaces.tool_search_strategy import ToolSearchStrategyConfigSerializer
        serializer = ToolSearchStrategyConfigSerializer()
        
        # This should work if the plugin is properly registered
        strategy_config = {
            "tool_search_strategy_type": "in_mem_embeddings",
            "model_name": "all-MiniLM-L6-v2",
            "similarity_threshold": 0.3
        }
        
        strategy = serializer.validate_dict(strategy_config)
        print(f"   ✅ Strategy created: {strategy.tool_search_strategy_type}")
        
        # Test 4: Basic functionality test
        print("4. Testing basic search functionality...")
        from utcp.data.tool import Tool, JsonSchema
        from utcp.data.call_template import CallTemplate
        from utcp.implementations.in_mem_tool_repository import InMemToolRepository
        
        # Create sample tools
        tools = [
            Tool(
                name="test.tool1",
                description="A test tool for cooking",
                inputs=JsonSchema(),
                outputs=JsonSchema(),
                tags=["cooking", "test"],
                tool_call_template=CallTemplate(
                    name="test.tool1",
                    description="Test tool",
                    call_template_type="default"
                )
            )
        ]
        
        # Create repository
        repo = InMemToolRepository()
        
        # Create a manual and add it to the repository
        from utcp.data.utcp_manual import UtcpManual
        manual = UtcpManual(tools=tools)
        manual_call_template = CallTemplate(name="test_manual", description="Test manual", call_template_type="default")
        await repo.save_manual(manual_call_template, manual)
       

        # Test search
        results = await strategy.search_tools(repo, "cooking", limit=1)
        print(f"   ✅ Search completed, found {len(results)} results")
        
        print("\n🎉 Integration test passed! Plugin works with core system.")
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_integration())
    sys.exit(0 if success else 1)
