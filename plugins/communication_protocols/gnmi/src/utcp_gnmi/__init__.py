from utcp.plugins.discovery import register_communication_protocol, register_call_template
from utcp_gnmi.gnmi_communication_protocol import GnmiCommunicationProtocol
from utcp_gnmi.gnmi_call_template import GnmiCallTemplateSerializer

def register():
    register_communication_protocol("gnmi", GnmiCommunicationProtocol())
    register_call_template("gnmi", GnmiCallTemplateSerializer())

__all__ = [
    "GnmiCommunicationProtocol",
    "GnmiCallTemplateSerializer",
]