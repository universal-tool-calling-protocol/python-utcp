from utcp_mcp.mcp_communication_protocol import McpCommunicationProtocol
from utcp_mcp.mcp_call_template import McpCallTemplate, McpCallTemplateSerializer
from utcp.plugins.discovery import register_communication_protocol, register_call_template

def register():
    register_communication_protocol("mcp", McpCommunicationProtocol())
    register_call_template("mcp", McpCallTemplateSerializer())

__all__ = [
    "McpCommunicationProtocol",
    "McpCallTemplate",
    "McpCallTemplateSerializer",
]
