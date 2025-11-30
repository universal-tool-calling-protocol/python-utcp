"""File Communication Protocol plugin for UTCP."""

from utcp.plugins.discovery import register_communication_protocol, register_call_template
from utcp_file.file_communication_protocol import FileCommunicationProtocol
from utcp_file.file_call_template import FileCallTemplate, FileCallTemplateSerializer


def register():
    register_communication_protocol("file", FileCommunicationProtocol())
    register_call_template("file", FileCallTemplateSerializer())


__all__ = [
    "FileCommunicationProtocol",
    "FileCallTemplate",
    "FileCallTemplateSerializer",
]
