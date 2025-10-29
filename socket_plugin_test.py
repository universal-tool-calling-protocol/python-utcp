import asyncio
import sys
from pathlib import Path

# Add core and plugin src paths so imports work without installing packages
core_src = Path(__file__).parent / "core" / "src"
socket_src = Path(__file__).parent / "plugins" / "communication_protocols" / "socket" / "src"
sys.path.insert(0, str(core_src.resolve()))
sys.path.insert(0, str(socket_src.resolve()))

from utcp.plugins.plugin_loader import ensure_plugins_initialized
from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplateSerializer
from utcp_socket import register as register_socket

async def main():
    # Manually register the socket plugin
    register_socket()

    # Load core plugins (auth, repo, search, post-processors)
    ensure_plugins_initialized()

    # 1. Check if communication protocols are registered
    registered_protocols = CommunicationProtocol.communication_protocols
    print(f"Registered communication protocols: {list(registered_protocols.keys())}")
    assert "tcp" in registered_protocols, "TCP communication protocol not registered"
    assert "udp" in registered_protocols, "UDP communication protocol not registered"
    print("✅ TCP and UDP communication protocols are registered.")

    # 2. Check if call templates are registered
    registered_serializers = CallTemplateSerializer.call_template_serializers
    print(f"Registered call template serializers: {list(registered_serializers.keys())}")
    assert "tcp" in registered_serializers, "TCP call template serializer not registered"
    assert "udp" in registered_serializers, "UDP call template serializer not registered"
    print("✅ TCP and UDP call template serializers are registered.")

    print("\n🎉 Socket plugin sanity check passed! 🎉")

if __name__ == "__main__":
    asyncio.run(main())