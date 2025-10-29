from utcp.plugins.discovery import register_communication_protocol, register_call_template
from utcp_socket.tcp_communication_protocol import TCPTransport
from utcp_socket.udp_communication_protocol import UDPTransport
from utcp_socket.tcp_call_template import TCPProviderSerializer
from utcp_socket.udp_call_template import UDPProviderSerializer


def register() -> None:
    # Register communication protocols
    register_communication_protocol("tcp", TCPTransport())
    register_communication_protocol("udp", UDPTransport())

    # Register call templates and their serializers
    register_call_template("tcp", TCPProviderSerializer())
    register_call_template("udp", UDPProviderSerializer())


__all__ = ["register"]