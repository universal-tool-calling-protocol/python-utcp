import sys
import os
import json
import time
import socket
import threading
import asyncio
from pathlib import Path

# Ensure core and socket plugin sources are on sys.path
ROOT = Path(__file__).resolve().parent.parent
CORE_SRC = ROOT / "core" / "src"
SOCKET_SRC = ROOT / "plugins" / "communication_protocols" / "socket" / "src"
for p in [str(CORE_SRC), str(SOCKET_SRC)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from utcp_socket.udp_communication_protocol import UDPTransport
from utcp_socket.tcp_communication_protocol import TCPTransport
from utcp_socket.udp_call_template import UDPProvider
from utcp_socket.tcp_call_template import TCPProvider

# -------------------------------
# Mock UDP Server
# -------------------------------

def start_udp_server(host: str, port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))

    def run():
        while True:
            data, addr = sock.recvfrom(65535)
            try:
                msg = data.decode("utf-8")
            except Exception:
                msg = ""
            # Handle discovery
            try:
                parsed = json.loads(msg)
            except Exception:
                parsed = None
            if isinstance(parsed, dict) and parsed.get("type") == "utcp":
                manual = {
                    "utcp_version": "1.0",
                    "manual_version": "1.0",
                    "tools": [
                        {
                            "name": "udp.echo",
                            "description": "Echo UDP args as JSON",
                            "inputs": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "extra": {"type": "number"}
                                },
                                "required": ["text"]
                            },
                            "outputs": {
                                "type": "object",
                                "properties": {
                                    "ok": {"type": "boolean"},
                                    "echo": {"type": "string"},
                                    "args": {"type": "object"}
                                }
                            },
                            "tags": ["socket", "udp"],
                            "average_response_size": 64,
                            # Return legacy provider to exercise conversion path
                            "tool_provider": {
                                "call_template_type": "udp",
                                "name": "udp",
                                "host": host,
                                "port": port,
                                "request_data_format": "json",
                                "response_byte_format": "utf-8",
                                "number_of_response_datagrams": 1,
                                "timeout": 3000
                            }
                        }
                    ]
                }
                payload = json.dumps(manual).encode("utf-8")
                sock.sendto(payload, addr)
            else:
                # Tool call: echo JSON payload
                try:
                    args = json.loads(msg)
                except Exception:
                    args = {"raw": msg}
                resp = {
                    "ok": True,
                    "echo": args.get("text", ""),
                    "args": args
                }
                sock.sendto(json.dumps(resp).encode("utf-8"), addr)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t

# -------------------------------
# Mock TCP Server (delimiter-based)\n
# -------------------------------

def start_tcp_server(host: str, port: int, delimiter: str = "\n"):
    delim_bytes = delimiter.encode("utf-8")

    def handle_client(conn: socket.socket, addr):
        try:
            # Read until delimiter
            buf = b""
            while True:
                chunk = conn.recv(1)
                if not chunk:
                    break
                buf += chunk
                if buf.endswith(delim_bytes):
                    break
            msg = buf[:-len(delim_bytes)].decode("utf-8") if buf.endswith(delim_bytes) else buf.decode("utf-8")
            # Discovery
            parsed = None
            try:
                parsed = json.loads(msg)
            except Exception:
                pass
            if isinstance(parsed, dict) and parsed.get("type") == "utcp":
                manual = {
                    "utcp_version": "1.0",
                    "manual_version": "1.0",
                    "tools": [
                        {
                            "name": "tcp.echo",
                            "description": "Echo TCP args as JSON",
                            "inputs": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "extra": {"type": "number"}
                                },
                                "required": ["text"]
                            },
                            "outputs": {
                                "type": "object",
                                "properties": {
                                    "ok": {"type": "boolean"},
                                    "echo": {"type": "string"},
                                    "args": {"type": "object"}
                                }
                            },
                            "tags": ["socket", "tcp"],
                            "average_response_size": 64,
                            # Legacy provider to exercise conversion
                            "tool_provider": {
                                "call_template_type": "tcp",
                                "name": "tcp",
                                "host": host,
                                "port": port,
                                "request_data_format": "json",
                                "response_byte_format": "utf-8",
                                "framing_strategy": "delimiter",
                                "message_delimiter": "\\n",
                                "timeout": 3000
                            }
                        }
                    ]
                }
                payload = json.dumps(manual).encode("utf-8") + delim_bytes
                conn.sendall(payload)
            else:
                # Tool call: echo JSON payload
                try:
                    args = json.loads(msg)
                except Exception:
                    args = {"raw": msg}
                resp = {
                    "ok": True,
                    "echo": args.get("text", ""),
                    "args": args
                }
                conn.sendall(json.dumps(resp).encode("utf-8") + delim_bytes)
        finally:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            conn.close()

    def run():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(5)
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t

# -------------------------------
# Sanity test runner
# -------------------------------

async def run_sanity():
    udp_host, udp_port = "127.0.0.1", 23456
    tcp_host, tcp_port = "127.0.0.1", 23457

    # Start servers
    start_udp_server(udp_host, udp_port)
    start_tcp_server(tcp_host, tcp_port, delimiter="\n")
    time.sleep(0.2)  # small delay to ensure servers are listening

    # Transports
    udp_transport = UDPTransport()
    tcp_transport = TCPTransport()

    # Register manuals
    udp_manual_template = UDPProvider(name="udp", host=udp_host, port=udp_port, request_data_format="json", response_byte_format="utf-8", number_of_response_datagrams=1, timeout=3000)
    tcp_manual_template = TCPProvider(name="tcp", host=tcp_host, port=tcp_port, request_data_format="json", response_byte_format="utf-8", framing_strategy="delimiter", message_delimiter="\n", timeout=3000)

    udp_reg = await udp_transport.register_manual(None, udp_manual_template)
    tcp_reg = await tcp_transport.register_manual(None, tcp_manual_template)

    print("UDP register success:", udp_reg.success, "tools:", len(udp_reg.manual.tools))
    print("TCP register success:", tcp_reg.success, "tools:", len(tcp_reg.manual.tools))

    assert udp_reg.success and len(udp_reg.manual.tools) == 1
    assert tcp_reg.success and len(tcp_reg.manual.tools) == 1

    # Verify tool_call_template present
    assert udp_reg.manual.tools[0].tool_call_template.call_template_type == "udp"
    assert tcp_reg.manual.tools[0].tool_call_template.call_template_type == "tcp"

    # Call tools
    udp_result = await udp_transport.call_tool(None, "udp.echo", {"text": "hello", "extra": 42}, udp_reg.manual.tools[0].tool_call_template)
    tcp_result = await tcp_transport.call_tool(None, "tcp.echo", {"text": "world", "extra": 99}, tcp_reg.manual.tools[0].tool_call_template)

    print("UDP call result:", udp_result)
    print("TCP call result:", tcp_result)

    # Basic assertions on response shape
    def ensure_dict(s):
        if isinstance(s, (bytes, bytearray)):
            try:
                s = s.decode("utf-8")
            except Exception:
                return {}
        if isinstance(s, str):
            try:
                return json.loads(s)
            except Exception:
                return {"raw": s}
        return s if isinstance(s, dict) else {}

    udp_resp = ensure_dict(udp_result)
    tcp_resp = ensure_dict(tcp_result)

    assert udp_resp.get("ok") is True and udp_resp.get("echo") == "hello"
    assert tcp_resp.get("ok") is True and tcp_resp.get("echo") == "world"

    print("Sanity passed: UDP/TCP discovery and calls work with tool_call_template normalization.")

if __name__ == "__main__":
    asyncio.run(run_sanity())