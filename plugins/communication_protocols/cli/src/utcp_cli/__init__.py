from utcp.discovery import register_communication_protocol, register_call_template
from utcp_cli.cli_communication_protocol import CliCommunicationProtocol
from utcp_cli.cli_call_template import CliCallTemplate, CliCallTemplateSerializer

register_communication_protocol("cli", CliCommunicationProtocol())
register_call_template("cli", CliCallTemplateSerializer())

__all__ = [
    "CliCommunicationProtocol",
    "CliCallTemplate",
    "CliCallTemplateSerializer",
]

