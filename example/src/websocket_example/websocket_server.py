#!/usr/bin/env python3
"""
Mock WebSocket server implementing UTCP protocol for demonstration.

This server provides several example tools accessible via WebSocket:
- echo: Echo back messages  
- calculate: Perform basic math operations
- get_time: Return current timestamp
- simulate_error: Demonstrate error handling

Run this server and then use websocket_client.py to interact with it.
"""

import asyncio
import json
import logging
import time
from aiohttp import web, WSMsgType
from aiohttp.web import Application, WebSocketResponse


class UTCPWebSocketServer:
    """WebSocket server implementing UTCP protocol"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.tools = self._define_tools()
    
    def _define_tools(self):
        """Define the tools available on this server"""
        return [
            {
                "name": "echo",
                "description": "Echo back the input message",
                "inputs": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "The message to echo back"
                        }
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
                "name": "calculate",
                "description": "Perform basic mathematical operations",
                "inputs": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["add", "subtract", "multiply", "divide"],
                            "description": "The operation to perform"
                        },
                        "a": {
                            "type": "number",
                            "description": "First operand"
                        },
                        "b": {
                            "type": "number", 
                            "description": "Second operand"
                        }
                    },
                    "required": ["operation", "a", "b"]
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
                "name": "get_time",
                "description": "Get the current server time",
                "inputs": {
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "enum": ["timestamp", "iso", "human"],
                            "description": "Time format to return"
                        }
                    }
                },
                "outputs": {
                    "type": "object",
                    "properties": {
                        "time": {"type": "string"},
                        "timestamp": {"type": "number"}
                    }
                },
                "tags": ["time", "utility"]
            },
            {
                "name": "simulate_error",
                "description": "Simulate an error for testing error handling",
                "inputs": {
                    "type": "object",
                    "properties": {
                        "error_type": {
                            "type": "string",
                            "enum": ["validation", "runtime", "custom"],
                            "description": "Type of error to simulate"
                        },
                        "message": {
                            "type": "string",
                            "description": "Custom error message"
                        }
                    }
                },
                "outputs": {
                    "type": "object",
                    "properties": {}
                },
                "tags": ["test", "error"]
            }
        ]
    
    async def websocket_handler(self, request):
        """Handle WebSocket connections"""
        ws = WebSocketResponse()
        await ws.prepare(request)
        
        client_info = f"{request.remote}:{request.transport.get_extra_info('peername')[1] if request.transport else 'unknown'}"
        self.logger.info(f"WebSocket connection from {client_info}")
        
        # Log any authentication headers
        auth_header = request.headers.get('Authorization')
        if auth_header:
            self.logger.info(f"Authentication: {auth_header[:20]}...")
        
        api_key = request.headers.get('X-API-Key')
        if api_key:
            self.logger.info("API Key header provided")
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_message(ws, msg.data, client_info)
                elif msg.type == WSMsgType.ERROR:
                    self.logger.error(f"WebSocket error: {ws.exception()}")
                    break
        except Exception as e:
            self.logger.error(f"Error in WebSocket handler: {e}")
        finally:
            self.logger.info(f"WebSocket connection closed: {client_info}")
        
        return ws
    
    async def _handle_message(self, ws, data, client_info):
        """Handle incoming WebSocket messages"""
        try:
            message = json.loads(data)
            message_type = message.get("type")
            request_id = message.get("request_id")
            
            self.logger.info(f"[{client_info}] Received {message_type} (ID: {request_id})")
            
            if message_type == "discover":
                await self._handle_discovery(ws, request_id)
            elif message_type == "call_tool":
                await self._handle_tool_call(ws, message, client_info)
            else:
                await self._send_error(ws, request_id, f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError as e:
            self.logger.error(f"[{client_info}] Invalid JSON: {e}")
            await self._send_error(ws, None, "Invalid JSON message")
        except Exception as e:
            self.logger.error(f"[{client_info}] Error handling message: {e}")
            await self._send_error(ws, None, f"Internal server error: {str(e)}")
    
    async def _handle_discovery(self, ws, request_id):
        """Handle tool discovery requests"""
        response = {
            "type": "discovery_response",
            "request_id": request_id,
            "tools": self.tools
        }
        await ws.send_str(json.dumps(response))
        self.logger.info(f"Sent discovery response with {len(self.tools)} tools")
    
    async def _handle_tool_call(self, ws, message, client_info):
        """Handle tool execution requests"""
        tool_name = message.get("tool_name")
        arguments = message.get("arguments", {})
        request_id = message.get("request_id")
        
        self.logger.info(f"[{client_info}] Executing {tool_name}: {arguments}")
        
        try:
            result = await self._execute_tool(tool_name, arguments)
            response = {
                "type": "tool_response",
                "request_id": request_id,
                "result": result
            }
            await ws.send_str(json.dumps(response))
            self.logger.info(f"[{client_info}] Tool {tool_name} completed successfully")
            
        except Exception as e:
            self.logger.error(f"[{client_info}] Tool {tool_name} failed: {e}")
            await self._send_tool_error(ws, request_id, str(e))
    
    async def _execute_tool(self, tool_name, arguments):
        """Execute a specific tool"""
        if tool_name == "echo":
            message = arguments.get("message", "")
            return {"echo": message}
            
        elif tool_name == "calculate":
            operation = arguments.get("operation")
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            
            if operation == "add":
                result = a + b
            elif operation == "subtract":
                result = a - b
            elif operation == "multiply":
                result = a * b
            elif operation == "divide":
                if b == 0:
                    raise ValueError("Division by zero")
                result = a / b
            else:
                raise ValueError(f"Unknown operation: {operation}")
            
            return {"result": result}
            
        elif tool_name == "get_time":
            format_type = arguments.get("format", "timestamp")
            current_time = time.time()
            
            if format_type == "timestamp":
                return {"time": str(current_time), "timestamp": current_time}
            elif format_type == "iso":
                from datetime import datetime
                iso_time = datetime.fromtimestamp(current_time).isoformat()
                return {"time": iso_time, "timestamp": current_time}
            elif format_type == "human":
                from datetime import datetime
                human_time = datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S")
                return {"time": human_time, "timestamp": current_time}
            else:
                raise ValueError(f"Unknown format: {format_type}")
                
        elif tool_name == "simulate_error":
            error_type = arguments.get("error_type", "runtime")
            custom_message = arguments.get("message", "Simulated error")
            
            if error_type == "validation":
                raise ValueError(f"Validation error: {custom_message}")
            elif error_type == "runtime":
                raise RuntimeError(f"Runtime error: {custom_message}")
            elif error_type == "custom":
                raise Exception(custom_message)
            else:
                raise ValueError(f"Unknown error type: {error_type}")
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
    
    async def _send_error(self, ws, request_id, error_message):
        """Send a general error response"""
        response = {
            "type": "error",
            "request_id": request_id,
            "error": error_message
        }
        await ws.send_str(json.dumps(response))
    
    async def _send_tool_error(self, ws, request_id, error_message):
        """Send a tool-specific error response"""
        response = {
            "type": "tool_error",
            "request_id": request_id,
            "error": error_message
        }
        await ws.send_str(json.dumps(response))


async def create_app():
    """Create the aiohttp application"""
    app = Application()
    server = UTCPWebSocketServer()
    
    # WebSocket endpoint
    app.router.add_get('/ws', server.websocket_handler)
    
    # Health check endpoint
    async def health_check(request):
        return web.json_response({
            "status": "ok",
            "service": "utcp-websocket-server",
            "tools_available": len(server.tools)
        })
    
    app.router.add_get('/health', health_check)
    
    return app


async def main():
    """Run the WebSocket server"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    app = await create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, 'localhost', 8765)
    await site.start()
    
    print("🚀 UTCP WebSocket Server running!")
    print("📡 WebSocket: ws://localhost:8765/ws")
    print("🔍 Health check: http://localhost:8765/health")
    print("📚 Available tools: echo, calculate, get_time, simulate_error")
    print("⏹️  Press Ctrl+C to stop")
    
    try:
        await asyncio.Future()  # Run forever
    except KeyboardInterrupt:
        print("\n⏹️  Shutting down server...")
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())