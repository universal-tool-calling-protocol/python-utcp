from utcp_mcp.mcp_communication_protocol import McpCommunicationProtocol
from utcp_mcp.mcp_call_template import McpCallTemplate, McpCallTemplateSerializer
from utcp.plugins.discovery import register_communication_protocol_factory, register_call_template

def register():
    # A FACTORY, not an instance: this protocol holds live MCP sessions (and,
    # for stdio, child processes). Shared, every client in the process would
    # dial into one session cache — so a caller that creates a client per
    # tenant, per user, or per pooled connection would not actually be
    # isolating them, and one client's close() would drain everyone's
    # sessions. One instance per client gives each its own connections and its
    # own teardown.
    register_communication_protocol_factory("mcp", McpCommunicationProtocol)
    register_call_template("mcp", McpCallTemplateSerializer())

__all__ = [
    "McpCommunicationProtocol",
    "McpCallTemplate",
    "McpCallTemplateSerializer",
]
