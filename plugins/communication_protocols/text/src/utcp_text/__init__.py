"""Text Communication Protocol plugin for UTCP."""

from utcp.plugins.discovery import register_communication_protocol, register_call_template
from utcp_text.text_communication_protocol import TextCommunicationProtocol
from utcp_text.text_call_template import TextCallTemplate, TextCallTemplateSerializer

def register():
    register_communication_protocol("text", TextCommunicationProtocol())
    register_call_template("text", TextCallTemplateSerializer())

__all__ = [
    "TextCommunicationProtocol",
    "TextCallTemplate",
    "TextCallTemplateSerializer",
]
