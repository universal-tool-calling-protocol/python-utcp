"""
Mock WebSocket server for testing UTCP WebSocket transport.
This can be used for manual testing and development.
"""

import asyncio
import json
import logging
from aiohttp import web, WSMsgType
from aiohttp.web import Application, Request, WebSocketResponse


class MockWebSocketServer:
    """
    A mock WebSocket server that implements the UTCP WebSocket protocol for testing.
    
    Supports:
    - Tool discovery via 'discover' message type
    - Tool execution via 'call_tool' message type  
    - Error simulation
    - Authentication headers (for testing)
    """
    
    def __init__(self, tools=None):
        self.tools = tools or self._default_tools()
        self.logger = logging.getLogger(__name__)
    
    def _default_tools(self):
        """Default set of tools for testing"""
        return [
            {
                "name": "echo",
                "description": "Echoes back the input message",
                "inputs": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Message to echo"}
                    },
                    "required": ["message"]
                },
                "outputs": {
                    "type": "object",
                    "properties": {
                        "echo": {"type": "string"}
                    }
                },
                "tags": ["utility", "test"]
            },
            {
                "name": "add_numbers",
                "description": "Adds two numbers together",
                "inputs": {
                    "type": "object", 
                    "properties": {
                        "a": {"type": "number", "description": "First number"},
                        "b": {"type": "number", "description": "Second number"}
                    },
                    "required": ["a", "b"]
                },
                "outputs": {
                    "type": "object",
                    "properties": {
                        "result": {"type": "number"}
                    }
                },
                "tags": ["math", "calculation"]
            },
            {
                "name": "get_timestamp",
                "description": "Returns current Unix timestamp",
                "inputs": {
                    "type": "object",
                    "properties": {}
                },
                "outputs": {
                    "type": "object",
                    "properties": {
                        "timestamp": {"type": "number"}
                    }
                },
                "tags": ["time", "utility"]
            },
            {
                "name": "simulate_error",
                "description": "Tool that always returns an error (for testing)",
                "inputs": {
                    "type": "object",
                    "properties": {
                        "error_message": {"type": "string", "description": "Custom error message"}
                    }
                },
                "outputs": {
                    "type": "object",
                    "properties": {}
                },
                "tags": ["test", "error"]
            }
        ]
    
    async def websocket_handler(self, request: Request) -> WebSocketResponse:
        """Handle WebSocket connections"""
        ws = WebSocketResponse()
        await ws.prepare(request)
        
        self.logger.info(f"WebSocket connection established from {request.remote}")
        
        # Log authentication headers for testing
        auth_header = request.headers.get('Authorization')
        if auth_header:
            self.logger.info(f"Authentication header: {auth_header[:20]}...")
        
        api_key = request.headers.get('X-API-Key')
        if api_key:
            self.logger.info(f"API Key header: {api_key[:10]}...")
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_text_message(ws, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    self.logger.error(f"WebSocket error: {ws.exception()}")
                    break
                    
        except Exception as e:
            self.logger.error(f"Error in WebSocket handler: {e}")
        finally:
            self.logger.info("WebSocket connection closed")
        
        return ws
    
    async def _handle_text_message(self, ws: WebSocketResponse, data: str):
        """Handle incoming text messages"""
        try:
            message = json.loads(data)
            self.logger.info(f"Received message: {message.get('type', 'unknown')}")
            
            message_type = message.get("type")
            request_id = message.get("request_id")
            
            if message_type == "discover":
                await self._handle_discovery(ws, request_id)
            elif message_type == "call_tool":
                await self._handle_tool_call(ws, message)
            else:
                await self._send_error(ws, request_id, f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            await self._send_error(ws, None, "Invalid JSON message")
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
            await self._send_error(ws, None, f"Internal server error: {str(e)}")
    
    async def _handle_discovery(self, ws: WebSocketResponse, request_id: str):
        """Handle tool discovery requests"""
        response = {
            "type": "discovery_response",
            "request_id": request_id,
            "tools": self.tools
        }
        await ws.send_str(json.dumps(response))
        self.logger.info(f"Sent discovery response with {len(self.tools)} tools")
    
    async def _handle_tool_call(self, ws: WebSocketResponse, message: dict):
        """Handle tool execution requests"""
        tool_name = message.get("tool_name")
        arguments = message.get("arguments", {})
        request_id = message.get("request_id")
        
        self.logger.info(f"Executing tool: {tool_name} with args: {arguments}")
        
        try:
            result = await self._execute_tool(tool_name, arguments)
            response = {
                "type": "tool_response",
                "request_id": request_id,
                "result": result
            }
            await ws.send_str(json.dumps(response))
            
        except Exception as e:
            await self._send_tool_error(ws, request_id, str(e))
    
    async def _execute_tool(self, tool_name: str, arguments: dict) -> dict:
        """Execute a specific tool and return the result"""
        if tool_name == "echo":
            message = arguments.get("message", "")
            return {"echo": message}
            
        elif tool_name == "add_numbers":
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            return {"result": a + b}
            
        elif tool_name == "get_timestamp":
            import time
            return {"timestamp": time.time()}
            
        elif tool_name == "simulate_error":
            error_message = arguments.get("error_message", "Simulated error")
            raise RuntimeError(error_message)
            
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
    
    async def _send_error(self, ws: WebSocketResponse, request_id: str, error_message: str):
        """Send a general error response"""
        response = {
            "type": "error",
            "request_id": request_id,
            "error": error_message
        }
        await ws.send_str(json.dumps(response))
    
    async def _send_tool_error(self, ws: WebSocketResponse, request_id: str, error_message: str):
        """Send a tool-specific error response"""
        response = {
            "type": "tool_error", 
            "request_id": request_id,
            "error": error_message
        }
        await ws.send_str(json.dumps(response))


async def create_app() -> Application:
    """Create the aiohttp application with WebSocket endpoints"""
    app = Application()
    server = MockWebSocketServer()
    
    # Add WebSocket route
    app.router.add_get('/ws', server.websocket_handler)
    
    # Add a simple HTTP endpoint for health checks
    async def health_check(request):
        return web.json_response({"status": "ok", "service": "mock-websocket-server"})
    
    app.router.add_get('/health', health_check)
    
    return app


async def main():
    """Run the mock server standalone for manual testing"""
    logging.basicConfig(level=logging.INFO)
    
    app = await create_app()
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, 'localhost', 8765)
    await site.start()
    
    print("Mock WebSocket server running on ws://localhost:8765/ws")
    print("Health check available at http://localhost:8765/health")
    print("Press Ctrl+C to stop")
    
    try:
        await asyncio.Future()  # Run forever
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())