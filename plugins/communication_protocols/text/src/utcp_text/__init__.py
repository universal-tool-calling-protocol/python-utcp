"""Text Communication Protocol plugin for UTCP."""

from utcp.discovery import register_communication_protocol, register_call_template
from utcp_text.text_communication_protocol import TextCommunicationProtocol
from utcp_text.text_call_template import TextCallTemplate, TextCallTemplateSerializer

register_communication_protocol("text", TextCommunicationProtocol())

# Register call template serializers
register_call_template("text", TextCallTemplateSerializer())

# Export public API
__all__ = [
    "TextCommunicationProtocol",
    "TextCallTemplate",
    "TextCallTemplateSerializer",
]
