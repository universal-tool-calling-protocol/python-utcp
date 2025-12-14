import sys
from pathlib import Path
import pytest

plugin_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(plugin_src))

core_src = Path(__file__).parent.parent.parent.parent.parent / "core" / "src"
sys.path.insert(0, str(core_src))

from utcp.utcp_client import UtcpClient
from utcp_gnmi import register

@pytest.mark.asyncio
async def test_register_manual_and_tools():
    register()
    client = await UtcpClient.create(config={
        "manual_call_templates": [
            {
                "name": "routerA",
                "call_template_type": "gnmi",
                "target": "localhost:50051",
                "use_tls": False,
                "operation": "get"
            }
        ]
    })
    tools = await client.config.tool_repository.get_tools()
    names = [t.name for t in tools]
    assert any(n.startswith("routerA.") for n in names)
    assert any(n.endswith("subscribe") for n in names)

def test_serializer_roundtrip():
    from utcp_gnmi.gnmi_call_template import GnmiCallTemplateSerializer
    serializer = GnmiCallTemplateSerializer()
    data = {
        "name": "routerB",
        "call_template_type": "gnmi",
        "target": "localhost:50051",
        "use_tls": False,
        "metadata": {"authorization": "Bearer token"},
        "metadata_fields": ["tenant-id"],
        "operation": "set",
        "stub_module": "gnmi_pb2_grpc",
        "message_module": "gnmi_pb2"
    }
    obj = serializer.validate_dict(data)
    out = serializer.to_dict(obj)
    assert out["call_template_type"] == "gnmi"
    assert out["operation"] == "set"