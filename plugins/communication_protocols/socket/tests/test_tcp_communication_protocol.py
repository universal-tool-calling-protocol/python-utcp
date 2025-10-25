import asyncio
import json
import pytest

from utcp_socket.tcp_communication_protocol import TCPTransport
from utcp_socket.tcp_call_template import TCPProvider


async def start_tcp_server():
    """Start a simple TCP server that sends a mutable JSON object then closes."""
    response_container = {"bytes": b""}

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            # Read any incoming data to simulate request handling
            await reader.read(1024)
        except Exception:
            pass
        # Send response and close connection
        writer.write(response_container["bytes"])
        await writer.drain()
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

    server = await asyncio.start_server(handle, host="127.0.0.1", port=0)
    port = server.sockets[0].getsockname()[1]

    def set_response(obj):
        response_container["bytes"] = json.dumps(obj).encode("utf-8")

    return server, port, set_response


@pytest.mark.asyncio
async def test_register_manual_converts_legacy_tool_provider_tcp():
    """When manual returns legacy tool_provider, it is converted to tool_call_template."""
    # Start server and configure response after obtaining port
    server, port, set_response = await start_tcp_server()
    set_response({
        "tools": [
            {
                "name": "tcp_tool",
                "description": "Echo over TCP",
                "inputs": {},
                "outputs": {},
                "tool_provider": {
                    "call_template_type": "tcp",
                    "name": "tcp-executor",
                    "host": "127.0.0.1",
                    "port": port,
                    "request_data_format": "json",
                    "response_byte_format": "utf-8",
                    "framing_strategy": "stream",
                    "timeout": 2000
                }
            }
        ]
    })

    try:
        provider = TCPProvider(
            name="tcp-provider",
            host="127.0.0.1",
            port=port,
            request_data_format="json",
            response_byte_format="utf-8",
            framing_strategy="stream",
            timeout=2000
        )
        transport_client = TCPTransport()
        result = await transport_client.register_manual(None, provider)

        assert result.success
        assert result.manual is not None
        assert len(result.manual.tools) == 1
        tool = result.manual.tools[0]
        assert tool.tool_call_template.call_template_type == "tcp"
        assert isinstance(tool.tool_call_template, TCPProvider)
        assert tool.tool_call_template.host == "127.0.0.1"
        assert tool.tool_call_template.port == port
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_register_manual_validates_provided_tool_call_template_tcp():
    """When manual provides tool_call_template, it is validated and preserved."""
    server, port, set_response = await start_tcp_server()
    set_response({
        "tools": [
            {
                "name": "tcp_tool",
                "description": "Echo over TCP",
                "inputs": {},
                "outputs": {},
                "tool_call_template": {
                    "call_template_type": "tcp",
                    "name": "tcp-executor",
                    "host": "127.0.0.1",
                    "port": port,
                    "request_data_format": "json",
                    "response_byte_format": "utf-8",
                    "framing_strategy": "stream",
                    "timeout": 2000
                }
            }
        ]
    })

    try:
        provider = TCPProvider(
            name="tcp-provider",
            host="127.0.0.1",
            port=port,
            request_data_format="json",
            response_byte_format="utf-8",
            framing_strategy="stream",
            timeout=2000
        )
        transport_client = TCPTransport()
        result = await transport_client.register_manual(None, provider)

        assert result.success
        assert len(result.manual.tools) == 1
        tool = result.manual.tools[0]
        assert tool.tool_call_template.call_template_type == "tcp"
        assert isinstance(tool.tool_call_template, TCPProvider)
        assert tool.tool_call_template.host == "127.0.0.1"
        assert tool.tool_call_template.port == port
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_register_manual_fallbacks_to_manual_template_tcp():
    """When neither tool_provider nor tool_call_template is provided, fall back to manual template."""
    server, port, set_response = await start_tcp_server()
    set_response({
        "tools": [
            {
                "name": "tcp_tool",
                "description": "Echo over TCP",
                "inputs": {},
                "outputs": {}
            }
        ]
    })

    try:
        provider = TCPProvider(
            name="tcp-provider",
            host="127.0.0.1",
            port=port,
            request_data_format="json",
            response_byte_format="utf-8",
            framing_strategy="stream",
            timeout=2000
        )
        transport_client = TCPTransport()
        result = await transport_client.register_manual(None, provider)

        assert result.success
        assert len(result.manual.tools) == 1
        tool = result.manual.tools[0]
        assert tool.tool_call_template.call_template_type == "tcp"
        assert isinstance(tool.tool_call_template, TCPProvider)
        # Should match manual (discovery) provider values
        assert tool.tool_call_template.host == provider.host
        assert tool.tool_call_template.port == provider.port
        assert tool.tool_call_template.name == provider.name
    finally:
        server.close()
        await server.wait_closed()