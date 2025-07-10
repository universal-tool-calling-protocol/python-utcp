# server.py
from mcp.server.fastmcp import FastMCP
from typing import TypedDict, List, Any

# Create an MCP server
mcp = FastMCP("Demo")


# Define a TypedDict for structured output
class EchoResponse(TypedDict):
    reply: str


# Add an echo tool that the test is expecting
@mcp.tool()
def echo(message: str) -> EchoResponse:
    """This tool echoes back its input"""
    return EchoResponse(reply=f"you said: {message}")


# Add a simple tool without specified return type
@mcp.tool()
def greet(name: str) -> str:
    """This tool greets a person without structured output"""
    return f"Hello, {name}!"


# Add a tool that returns a list
@mcp.tool()
def list_items(count: int) -> List[str]:
    """This tool returns a list of items"""
    return [f"item_{i}" for i in range(count)]


# Add a tool that returns a number
@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """This tool adds two numbers"""
    return a + b


# Start the server when this script is run directly
if __name__ == "__main__":
    mcp.run()