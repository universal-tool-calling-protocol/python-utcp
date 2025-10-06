#!/usr/bin/env python3
"""
WebSocket client example demonstrating UTCP WebSocket transport.

This example shows how to:
1. Create a UTCP client with WebSocket transport
2. Discover tools from a WebSocket provider
3. Execute tools via WebSocket
4. Handle real-time responses

Make sure to run websocket_server.py first!
"""

import asyncio
import json
import logging
from utcp.client import UtcpClient


async def demonstrate_websocket_tools():
    """Demonstrate WebSocket transport capabilities"""
    print("🚀 UTCP WebSocket Client Example")
    print("=" * 50)
    
    # Create UTCP client with WebSocket provider
    print("📡 Connecting to WebSocket provider...")
    client = await UtcpClient.create(
        config={"providers_file_path": "./providers.json"}
    )
    
    try:
        # Discover available tools
        print("\n🔍 Discovering available tools...")
        all_tools = await client.get_all_tools()
        websocket_tools = [tool for tool in all_tools if tool.tool_provider.provider_type == "websocket"]
        
        print(f"Found {len(websocket_tools)} WebSocket tools:")
        for tool in websocket_tools:
            print(f"  • {tool.name}: {tool.description}")
            if tool.tags:
                print(f"    Tags: {', '.join(tool.tags)}")
        
        if not websocket_tools:
            print("❌ No WebSocket tools found. Make sure websocket_server.py is running!")
            return
        
        print("\n" + "=" * 50)
        print("🛠️  Testing WebSocket tools...")
        
        # Test echo tool
        print("\n1️⃣ Testing echo tool:")
        result = await client.call_tool(
            "websocket_tools.echo",
            {"message": "Hello from UTCP WebSocket client! 👋"}
        )
        print(f"   Echo result: {result}")
        
        # Test calculator
        print("\n2️⃣ Testing calculator tool:")
        calculations = [
            {"operation": "add", "a": 15, "b": 25},
            {"operation": "multiply", "a": 7, "b": 8},
            {"operation": "divide", "a": 100, "b": 4}
        ]
        
        for calc in calculations:
            result = await client.call_tool("websocket_tools.calculate", calc)
            op = calc["operation"]
            a, b = calc["a"], calc["b"]
            print(f"   {a} {op} {b} = {result['result']}")
        
        # Test time tool
        print("\n3️⃣ Testing time tool:")
        formats = ["timestamp", "iso", "human"]
        for fmt in formats:
            result = await client.call_tool("websocket_tools.get_time", {"format": fmt})
            print(f"   {fmt} format: {result['time']}")
        
        # Test error handling
        print("\n4️⃣ Testing error handling:")
        try:
            await client.call_tool(
                "websocket_tools.simulate_error",
                {"error_type": "validation", "message": "This is a test error"}
            )
        except Exception as e:
            print(f"   ✅ Error properly caught: {e}")
        
        # Test tool search
        print("\n🔎 Testing tool search...")
        math_tools = client.search_tools("math calculation")
        print(f"Found {len(math_tools)} tools for 'math calculation':")
        for tool in math_tools:
            print(f"  • {tool.name} (score: {getattr(tool, 'score', 'N/A')})")
        
        print("\n✅ All WebSocket transport tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during demonstration: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        await client.close()
        print("\n🔌 WebSocket connection closed")


async def interactive_mode():
    """Interactive mode for manual testing"""
    print("\n" + "=" * 50)
    print("🎮 Interactive Mode")
    print("Type 'help' for commands, 'exit' to quit")
    
    client = await UtcpClient.create(
        config={"providers_file_path": "./providers.json"}
    )
    
    try:
        while True:
            try:
                command = input("\n> ").strip()
                
                if command.lower() in ['exit', 'quit', 'q']:
                    break
                elif command.lower() == 'help':
                    print("""
Available commands:
  list                           - List all available tools
  call <tool_name> <json_args>  - Call a tool with JSON arguments
  search <query>                - Search for tools
  help                          - Show this help
  exit                          - Exit interactive mode

Examples:
  call websocket_tools.echo {"message": "Hello!"}
  call websocket_tools.calculate {"operation": "add", "a": 5, "b": 3}
  search math
                    """)
                elif command.startswith('list'):
                    tools = await client.get_all_tools()
                    ws_tools = [t for t in tools if t.tool_provider.provider_type == "websocket"]
                    for tool in ws_tools:
                        print(f"  {tool.name}: {tool.description}")
                
                elif command.startswith('call '):
                    parts = command[5:].split(' ', 1)
                    if len(parts) != 2:
                        print("Usage: call <tool_name> <json_args>")
                        continue
                    
                    tool_name, args_str = parts
                    try:
                        args = json.loads(args_str)
                        result = await client.call_tool(tool_name, args)
                        print(f"Result: {json.dumps(result, indent=2)}")
                    except json.JSONDecodeError:
                        print("Error: Invalid JSON arguments")
                    except Exception as e:
                        print(f"Error: {e}")
                
                elif command.startswith('search '):
                    query = command[7:]
                    tools = await client.search_tools(query)
                    print(f"Found {len(tools)} tools:")
                    for tool in tools:
                        print(f"  {tool.name}: {tool.description}")
                
                else:
                    print("Unknown command. Type 'help' for available commands.")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
    
    finally:
        await client.close()


async def main():
    """Main entry point"""
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Run demonstration
        await demonstrate_websocket_tools()
        
        # Ask if user wants interactive mode
        if input("\n🎮 Enter interactive mode? (y/N): ").lower().startswith('y'):
            await interactive_mode()
            
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())