#!/usr/bin/env python3
"""
Manual test script for WebSocket transport implementation.
This tests the core functionality without requiring pytest setup.
"""

import asyncio
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utcp.client.transport_interfaces.websocket_transport import WebSocketClientTransport
from utcp.shared.provider import WebSocketProvider
from utcp.shared.auth import ApiKeyAuth, BasicAuth


async def test_basic_functionality():
    """Test basic WebSocket transport functionality"""
    print("Testing WebSocket Transport Implementation...")
    
    transport = WebSocketClientTransport()
    
    # Test 1: Security enforcement
    print("\n1. Testing security enforcement...")
    try:
        insecure_provider = WebSocketProvider(
            name="insecure",
            url="ws://example.com/ws"  # Should be rejected
        )
        await transport.register_tool_provider(insecure_provider)
        print("❌ FAILED: Insecure URL was accepted")
    except ValueError as e:
        if "Security error" in str(e):
            print("✅ PASSED: Insecure URL properly rejected")
        else:
            print(f"❌ FAILED: Wrong error: {e}")
    except Exception as e:
        print(f"❌ FAILED: Unexpected error: {e}")
    
    # Test 2: Provider type validation
    print("\n2. Testing provider type validation...")
    try:
        from utcp.shared.provider import HttpProvider
        wrong_provider = HttpProvider(name="wrong", url="https://example.com")
        await transport.register_tool_provider(wrong_provider)
        print("❌ FAILED: Wrong provider type was accepted")
    except ValueError as e:
        if "WebSocketClientTransport can only be used with WebSocketProvider" in str(e):
            print("✅ PASSED: Provider type validation works")
        else:
            print(f"❌ FAILED: Wrong error: {e}")
    except Exception as e:
        print(f"❌ FAILED: Unexpected error: {e}")
    
    # Test 3: Authentication header preparation
    print("\n3. Testing authentication...")
    try:
        # Test API Key auth
        api_provider = WebSocketProvider(
            name="api_test",
            url="wss://example.com/ws",
            auth=ApiKeyAuth(
                var_name="X-API-Key",
                api_key="test-key-123",
                location="header"
            )
        )
        headers = await transport._prepare_headers(api_provider)
        if headers.get("X-API-Key") == "test-key-123":
            print("✅ PASSED: API Key authentication headers prepared correctly")
        else:
            print(f"❌ FAILED: API Key headers incorrect: {headers}")
        
        # Test Basic auth
        basic_provider = WebSocketProvider(
            name="basic_test", 
            url="wss://example.com/ws",
            auth=BasicAuth(username="user", password="pass")
        )
        headers = await transport._prepare_headers(basic_provider)
        if "Authorization" in headers and headers["Authorization"].startswith("Basic "):
            print("✅ PASSED: Basic authentication headers prepared correctly")
        else:
            print(f"❌ FAILED: Basic auth headers incorrect: {headers}")
            
    except Exception as e:
        print(f"❌ FAILED: Authentication test error: {e}")
    
    # Test 4: Connection management 
    print("\n4. Testing connection management...")
    try:
        localhost_provider = WebSocketProvider(
            name="test_provider",
            url="ws://localhost:8765/ws"
        )
        
        # This should fail to connect but not due to security
        try:
            await transport.register_tool_provider(localhost_provider)
            print("❌ FAILED: Connection should have failed (no server)")
        except ValueError as e:
            if "Security error" in str(e):
                print("❌ FAILED: Security error on localhost")
            else:
                print("❓ UNEXPECTED: Different error occurred")
        except Exception as e:
            # Expected - connection refused or similar
            print("✅ PASSED: Connection management works (failed to connect as expected)")
            
    except Exception as e:
        print(f"❌ FAILED: Connection test error: {e}")
    
    # Test 5: Cleanup
    print("\n5. Testing cleanup...")
    try:
        await transport.close()
        if len(transport._connections) == 0 and len(transport._oauth_tokens) == 0:
            print("✅ PASSED: Cleanup successful")
        else:
            print("❌ FAILED: Cleanup incomplete")
    except Exception as e:
        print(f"❌ FAILED: Cleanup error: {e}")
    
    print("\n✅ WebSocket transport basic functionality tests completed!")


async def test_with_mock_server():
    """Test with a real WebSocket connection to our mock server"""
    print("\n" + "="*50)
    print("Testing with Mock WebSocket Server")
    print("="*50)
    
    # Import and start mock server
    sys.path.append('tests/client/transport_interfaces')
    try:
        from mock_websocket_server import create_app
        from aiohttp import web
        
        print("Starting mock WebSocket server...")
        app = await create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', 8765)
        await site.start()
        
        print("Mock server started on ws://localhost:8765/ws")
        
        # Test with our transport
        transport = WebSocketClientTransport()
        provider = WebSocketProvider(
            name="test_provider",
            url="ws://localhost:8765/ws"
        )
        
        try:
            # Test tool discovery
            print("\nTesting tool discovery...")
            tools = await transport.register_tool_provider(provider)
            print(f"✅ Discovered {len(tools)} tools:")
            for tool in tools:
                print(f"  - {tool.name}: {tool.description}")
            
            # Test tool execution
            print("\nTesting tool execution...")
            result = await transport.call_tool("echo", {"message": "Hello WebSocket!"}, provider)
            print(f"✅ Echo result: {result}")
            
            result = await transport.call_tool("add_numbers", {"a": 5, "b": 3}, provider)
            print(f"✅ Add result: {result}")
            
            # Test error handling
            print("\nTesting error handling...")
            try:
                await transport.call_tool("simulate_error", {"error_message": "Test error"}, provider)
                print("❌ FAILED: Error tool should have failed")
            except RuntimeError as e:
                print(f"✅ Error properly handled: {e}")
            
        except Exception as e:
            print(f"❌ Transport test failed: {e}")
        finally:
            await transport.close()
            await runner.cleanup()
            print("Mock server stopped")
            
    except ImportError as e:
        print(f"⚠️  Mock server test skipped (missing dependencies): {e}")
    except Exception as e:
        print(f"❌ Mock server test failed: {e}")


async def main():
    """Run all manual tests"""
    await test_basic_functionality()
    # await test_with_mock_server()  # Uncomment if you want to test with real server


if __name__ == "__main__":
    asyncio.run(main())