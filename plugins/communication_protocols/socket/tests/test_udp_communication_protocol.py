import asyncio
import json
import pytest

from utcp_socket.udp_communication_protocol import UDPTransport
from utcp_socket.udp_call_template import UDPProvider


async def start_udp_server():
    """Start a simple UDP server that replies with a mutable JSON payload."""
    loop = asyncio.get_running_loop()
    response_container = {"bytes": b""}

    class _Protocol(asyncio.DatagramProtocol):
        def __init__(self, container):
            self.container = container
            self.transport = None

        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, addr):
            # Always respond with the prepared payload
            if self.transport:
                self.transport.sendto(self.container["bytes"], addr)

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: _Protocol(response_container), local_addr=("127.0.0.1", 0)
    )
    port = transport.get_extra_info("socket").getsockname()[1]

    def set_response(obj):
        response_container["bytes"] = json.dumps(obj).encode("utf-8")

    return transport, port, set_response


@pytest.mark.asyncio
async def test_register_manual_converts_legacy_tool_provider_udp():
    """When manual returns legacy tool_provider, it is converted to tool_call_template."""
    # Start server and configure response after obtaining port
    transport, port, set_response = await start_udp_server()
    set_response({
        "tools": [
            {
                "name": "udp_tool",
                "description": "Echo over UDP",
                "inputs": {},
                "outputs": {},
                "tool_provider": {
                    "call_template_type": "udp",
                    "name": "udp-executor",
                    "host": "127.0.0.1",
                    "port": port,
                    "number_of_response_datagrams": 1,
                    "request_data_format": "json",
                    "response_byte_format": "utf-8",
                    "timeout": 2000
                }
            }
        ]
    })

    try:
        provider = UDPProvider(
            name="udp-provider",
            host="127.0.0.1",
            port=port,
            number_of_response_datagrams=1,
            request_data_format="json",
            response_byte_format="utf-8",
            timeout=2000
        )
        transport_client = UDPTransport()
        result = await transport_client.register_manual(None, provider)

        assert result.success
        assert result.manual is not None
        assert len(result.manual.tools) == 1
        tool = result.manual.tools[0]
        assert tool.tool_call_template.call_template_type == "udp"
        assert isinstance(tool.tool_call_template, UDPProvider)
        assert tool.tool_call_template.host == "127.0.0.1"
        assert tool.tool_call_template.port == port
    finally:
        transport.close()


@pytest.mark.asyncio
async def test_register_manual_validates_provided_tool_call_template_udp():
    """When manual provides tool_call_template, it is validated and preserved."""
    transport, port, set_response = await start_udp_server()
    set_response({
        "tools": [
            {
                "name": "udp_tool",
                "description": "Echo over UDP",
                "inputs": {},
                "outputs": {},
                "tool_call_template": {
                    "call_template_type": "udp",
                    "name": "udp-executor",
                    "host": "127.0.0.1",
                    "port": port,
                    "number_of_response_datagrams": 1,
                    "request_data_format": "json",
                    "response_byte_format": "utf-8",
                    "timeout": 2000
                }
            }
        ]
    })

    try:
        provider = UDPProvider(
            name="udp-provider",
            host="127.0.0.1",
            port=port,
            number_of_response_datagrams=1,
            request_data_format="json",
            response_byte_format="utf-8",
            timeout=2000
        )
        transport_client = UDPTransport()
        result = await transport_client.register_manual(None, provider)

        assert result.success
        assert len(result.manual.tools) == 1
        tool = result.manual.tools[0]
        assert tool.tool_call_template.call_template_type == "udp"
        assert isinstance(tool.tool_call_template, UDPProvider)
        assert tool.tool_call_template.host == "127.0.0.1"
        assert tool.tool_call_template.port == port
    finally:
        transport.close()


@pytest.mark.asyncio
async def test_register_manual_fallbacks_to_manual_template_udp():
    """When neither tool_provider nor tool_call_template is provided, fall back to manual template."""
    transport, port, set_response = await start_udp_server()
    set_response({
        "tools": [
            {
                "name": "udp_tool",
                "description": "Echo over UDP",
                "inputs": {},
                "outputs": {}
            }
        ]
    })

    try:
        provider = UDPProvider(
            name="udp-provider",
            host="127.0.0.1",
            port=port,
            number_of_response_datagrams=1,
            request_data_format="json",
            response_byte_format="utf-8",
            timeout=2000
        )
        transport_client = UDPTransport()
        result = await transport_client.register_manual(None, provider)

        assert result.success
        assert len(result.manual.tools) == 1
        tool = result.manual.tools[0]
        assert tool.tool_call_template.call_template_type == "udp"
        assert isinstance(tool.tool_call_template, UDPProvider)
        # Should match manual (discovery) provider values
        assert tool.tool_call_template.host == provider.host
        assert tool.tool_call_template.port == provider.port
        assert tool.tool_call_template.name == provider.name
    finally:
        transport.close()