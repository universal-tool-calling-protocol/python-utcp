"""WebSocket Communication Protocol plugin for UTCP.

This plugin provides WebSocket-based real-time bidirectional communication protocol.
"""

from utcp.plugins.discovery import register_communication_protocol_factory, register_call_template
from utcp_websocket.websocket_communication_protocol import WebSocketCommunicationProtocol
from utcp_websocket.websocket_call_template import WebSocketCallTemplate, WebSocketCallTemplateSerializer

def register():
    """Register the WebSocket communication protocol and call template serializer."""
    # A FACTORY, not an instance: this protocol keeps one live WebSocket per
    # manual name and URL. Shared, two clients registering the same manual
    # would use — and on deregistration close — each other's connection, and
    # one client's close() would drop everyone's. One instance per client
    # gives each its own connections and its own teardown.
    register_communication_protocol_factory("websocket", WebSocketCommunicationProtocol)

    # Register call template serializer
    register_call_template("websocket", WebSocketCallTemplateSerializer())

# Export public API
__all__ = [
    "WebSocketCommunicationProtocol",
    "WebSocketCallTemplate",
    "WebSocketCallTemplateSerializer",
]
