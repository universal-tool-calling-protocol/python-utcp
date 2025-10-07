"""WebSocket Communication Protocol plugin for UTCP.

This plugin provides WebSocket-based real-time bidirectional communication protocol.
"""

from utcp.plugins.discovery import register_communication_protocol, register_call_template
from utcp_websocket.websocket_communication_protocol import WebSocketCommunicationProtocol
from utcp_websocket.websocket_call_template import WebSocketCallTemplate, WebSocketCallTemplateSerializer

def register():
    """Register the WebSocket communication protocol and call template serializer."""
    # Register WebSocket communication protocol
    register_communication_protocol("websocket", WebSocketCommunicationProtocol())

    # Register call template serializer
    register_call_template("websocket", WebSocketCallTemplateSerializer())

# Export public API
__all__ = [
    "WebSocketCommunicationProtocol",
    "WebSocketCallTemplate",
    "WebSocketCallTemplateSerializer",
]
