from utcp.data.auth import Auth, AuthSerializer
from utcp.data.variable_loader import VariableLoader, VariableLoaderSerializer
from utcp.interfaces.serializer import Serializer
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository, ConcurrentToolRepositoryConfigSerializer
from utcp.interfaces.tool_search_strategy import ToolSearchStrategy, ToolSearchStrategyConfigSerializer
from utcp.interfaces.tool_post_processor import ToolPostProcessor, ToolPostProcessorConfigSerializer
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

def register_tool_repository(tool_repository_type: str, tool_repository: Serializer[ConcurrentToolRepository], override: bool = False) -> bool:
    if not override and tool_repository_type in ConcurrentToolRepositoryConfigSerializer.tool_repository_implementations:
        return False
    ConcurrentToolRepositoryConfigSerializer.tool_repository_implementations[tool_repository_type] = tool_repository
    return True

def register_tool_search_strategy(strategy_type: str, strategy: Serializer[ToolSearchStrategy], override: bool = False) -> bool:
    if not override and strategy_type in ToolSearchStrategyConfigSerializer.tool_search_strategy_implementations:
        return False
    ToolSearchStrategyConfigSerializer.tool_search_strategy_implementations[strategy_type] = strategy
    return True

def register_tool_post_processor(tool_post_processor_type: str, tool_post_processor: Serializer[ToolPostProcessor], override: bool = False) -> bool:
    if not override and tool_post_processor_type in ToolPostProcessorConfigSerializer.tool_post_processor_implementations:
        return False
    ToolPostProcessorConfigSerializer.tool_post_processor_implementations[tool_post_processor_type] = tool_post_processor
    return True
