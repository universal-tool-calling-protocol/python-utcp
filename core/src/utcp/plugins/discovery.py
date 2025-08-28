from utcp.data.auth import Auth, AuthSerializer
from utcp.data.variable_loader import VariableLoader, VariableLoaderSerializer
from utcp.interfaces.serializer import Serializer
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository, ConcurrentToolRepositoryConfigSerializer
from utcp.interfaces.tool_search_strategy import ToolSearchStrategy, ToolSearchStrategyConfigSerializer
from utcp.interfaces.tool_post_processor import ToolPostProcessor, ToolPostProcessorConfigSerializer
from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplate, CallTemplateSerializer
import logging

logger = logging.getLogger(__name__)

def register_auth(auth_type: str, serializer: Serializer[Auth], override: bool = False) -> bool:
    """REQUIRED
    Register an authentication implementation.

    Args:
        auth_type: The authentication type identifier.
        serializer: The serializer for the authentication implementation.
        override: Whether to override an existing implementation.

    Returns:
        True if the implementation was registered, False otherwise.
    """
    if not override and auth_type in AuthSerializer.auth_serializers:
        return False
    AuthSerializer.auth_serializers[auth_type] = serializer
    logger.info("Registered auth type: " + auth_type)
    return True

def register_variable_loader(loader_type: str, serializer: Serializer[VariableLoader], override: bool = False) -> bool:
    """REQUIRED
    Register a variable loader implementation.

    Args:
        loader_type: The variable loader type identifier.
        serializer: The serializer for the variable loader implementation.
        override: Whether to override an existing implementation.

    Returns:
        True if the implementation was registered, False otherwise.
    """
    if not override and loader_type in VariableLoaderSerializer.loader_serializers:
        return False
    VariableLoaderSerializer.loader_serializers[loader_type] = serializer
    logger.info("Registered variable loader type: " + loader_type)
    return True

def register_call_template(call_template_type: str, serializer: Serializer[CallTemplate], override: bool = False) -> bool:
    """REQUIRED
    Register a call template implementation.

    Args:
        call_template_type: The call template type identifier.
        serializer: The serializer for the call template implementation.
        override: Whether to override an existing implementation.

    Returns:
        True if the implementation was registered, False otherwise.
    """
    if not override and call_template_type in CallTemplateSerializer.call_template_serializers:
        return False
    CallTemplateSerializer.call_template_serializers[call_template_type] = serializer
    logger.info("Registered call template type: " + call_template_type)
    return True

def register_communication_protocol(communication_protocol_type: str, communication_protocol: CommunicationProtocol, override: bool = False) -> bool:
    """REQUIRED
    Register a communication protocol implementation.

    Args:
        communication_protocol_type: The communication protocol type identifier.
        communication_protocol: The communication protocol implementation.
        override: Whether to override an existing implementation.

    Returns:
        True if the implementation was registered, False otherwise.
    """
    if not override and communication_protocol_type in CommunicationProtocol.communication_protocols:
        return False
    CommunicationProtocol.communication_protocols[communication_protocol_type] = communication_protocol
    logger.info("Registered communication protocol type: " + communication_protocol_type)
    return True

def register_tool_repository(tool_repository_type: str, tool_repository: Serializer[ConcurrentToolRepository], override: bool = False) -> bool:
    """REQUIRED
    Register a tool repository implementation.

    Args:
        tool_repository_type: The tool repository type identifier.
        tool_repository: The tool repository implementation.
        override: Whether to override an existing implementation.

    Returns:
        True if the implementation was registered, False otherwise.
    """
    if not override and tool_repository_type in ConcurrentToolRepositoryConfigSerializer.tool_repository_implementations:
        return False
    ConcurrentToolRepositoryConfigSerializer.tool_repository_implementations[tool_repository_type] = tool_repository
    logger.info("Registered tool repository type: " + tool_repository_type)
    return True

def register_tool_search_strategy(strategy_type: str, strategy: Serializer[ToolSearchStrategy], override: bool = False) -> bool:
    """REQUIRED
    Register a tool search strategy implementation.

    Args:
        strategy_type: The tool search strategy type identifier.
        strategy: The tool search strategy implementation.
        override: Whether to override an existing implementation.

    Returns:
        True if the implementation was registered, False otherwise.
    """
    if not override and strategy_type in ToolSearchStrategyConfigSerializer.tool_search_strategy_implementations:
        return False
    ToolSearchStrategyConfigSerializer.tool_search_strategy_implementations[strategy_type] = strategy
    logger.info("Registered tool search strategy type: " + strategy_type)
    return True

def register_tool_post_processor(tool_post_processor_type: str, tool_post_processor: Serializer[ToolPostProcessor], override: bool = False) -> bool:
    """REQUIRED
    Register a tool post processor implementation.

    Args:
        tool_post_processor_type: The tool post processor type identifier.
        tool_post_processor: The tool post processor implementation.
        override: Whether to override an existing implementation.

    Returns:
        True if the implementation was registered, False otherwise.
    """
    if not override and tool_post_processor_type in ToolPostProcessorConfigSerializer.tool_post_processor_implementations:
        return False
    ToolPostProcessorConfigSerializer.tool_post_processor_implementations[tool_post_processor_type] = tool_post_processor
    logger.info("Registered tool post processor type: " + tool_post_processor_type)
    return True
