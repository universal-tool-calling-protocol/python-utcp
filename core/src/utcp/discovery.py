from utcp.data.auth import Auth, AuthSerializer
from utcp.data.variable_loader import VariableLoader, VariableLoaderSerializer
from utcp.interfaces.serializer import Serializer
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository
from utcp.interfaces.tool_search_strategy import ToolSearchStrategy
from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplate, CallTemplateSerializer
import sys

def register_auth(auth_type: str, serializer: Serializer[Auth], override: bool = False) -> bool:
    if not override and auth_type in AuthSerializer.auth_serializers:
        return False
    AuthSerializer.auth_serializers[auth_type] = serializer
    return True

def register_variable_loader(loader_type: str, serializer: Serializer[VariableLoader], override: bool = False) -> bool:
    if not override and loader_type in VariableLoaderSerializer.loader_serializers:
        return False
    VariableLoaderSerializer.loader_serializers[loader_type] = serializer
    return True

def register_call_template(call_template_type: str, serializer: Serializer[CallTemplate], override: bool = False) -> bool:
    if not override and call_template_type in CallTemplateSerializer.call_template_serializers:
        return False
    print("Registering call template: " + call_template_type, file=sys.stderr)
    CallTemplateSerializer.call_template_serializers[call_template_type] = serializer
    return True

def register_communication_protocol(communication_protocol_type: str, communication_protocol: CommunicationProtocol, override: bool = False) -> bool:
    if not override and communication_protocol_type in CommunicationProtocol.communication_protocols:
        return False
    CommunicationProtocol.communication_protocols[communication_protocol_type] = communication_protocol
    return True

def register_tool_repository(tool_repository_name: str, tool_repository: ConcurrentToolRepository, override: bool = False) -> bool:
    if not override and tool_repository_name in ConcurrentToolRepository.tool_repository_implementations:
        return False
    ConcurrentToolRepository.tool_repository_implementations[tool_repository_name] = tool_repository
    return True

def register_tool_search_strategy(strategy_name: str, strategy: ToolSearchStrategy, override: bool = False) -> bool:
    if not override and strategy_name in ToolSearchStrategy.tool_search_strategy_implementations:
        return False
    ToolSearchStrategy.tool_search_strategy_implementations[strategy_name] = strategy
    return True
