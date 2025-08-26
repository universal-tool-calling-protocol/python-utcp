from abc import ABC, abstractmethod
from utcp.utcp_client import UtcpClient
from utcp.data.tool import Tool
from utcp.data.call_template import CallTemplate
from typing import Any, Dict
from utcp.interfaces.serializer import Serializer
from pydantic import BaseModel
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class ToolPostProcessor(BaseModel, ABC):
    """REQUIRED
    Abstract interface for tool post processors.

    Defines the contract for tool post processors that process the result of a tool call.
    Tool post processors are responsible for:
    - Processing the result of a tool call
    - Returning the processed result
    """
    tool_post_processor_type: str

    @abstractmethod
    def post_process(self, caller: 'UtcpClient', tool: Tool, manual_call_template: 'CallTemplate', result: Any) -> Any:
        """REQUIRED
        Process the result of a tool call.

        Args:
            caller: The UTCP client that is calling this method.
            tool: The tool that was called.
            manual_call_template: The call template of the manual that was called.
            result: The result of the tool call.

        Returns:
            The processed result.
        """
        raise NotImplementedError

class ToolPostProcessorConfigSerializer(Serializer[ToolPostProcessor]):
    """REQUIRED
    Serializer for tool post processors.

    Defines the contract for serializers that convert tool post processors to and from
    dictionaries for storage or transmission. Serializers are responsible for:
    - Converting tool post processors to dictionaries for storage or transmission
    - Converting dictionaries back to tool post processors
    - Ensuring data consistency during serialization and deserialization
    """
    tool_post_processor_implementations: Dict[str, Serializer[ToolPostProcessor]] = {}
    
    def to_dict(self, obj: ToolPostProcessor) -> dict:
        """REQUIRED
        Convert a tool post processor to a dictionary.

        Args:
            obj: The tool post processor to convert.

        Returns:
            The dictionary converted from the tool post processor.
        """
        return ToolPostProcessorConfigSerializer.tool_post_processor_implementations[obj.tool_post_processor_type].to_dict(obj)
    
    def validate_dict(self, data: dict) -> ToolPostProcessor:
        """REQUIRED
        Validate a dictionary and convert it to a tool post processor.

        Args:
            data: The dictionary to validate and convert.

        Returns:
            The tool post processor converted from the dictionary.
        """
        try:
            return ToolPostProcessorConfigSerializer.tool_post_processor_implementations[data['tool_post_processor_type']].validate_dict(data)
        except KeyError:
            raise ValueError(f"Invalid tool post processor type: {data['tool_post_processor_type']}")
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid ToolPostProcessor: " + traceback.format_exc()) from e
