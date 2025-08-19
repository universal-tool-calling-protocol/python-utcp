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
    tool_post_processor_type: str

    @abstractmethod
    def post_process(self, caller: 'UtcpClient', tool: Tool, manual_call_template: 'CallTemplate', result: Any) -> Any:
        raise NotImplementedError

class ToolPostProcessorConfigSerializer(Serializer[ToolPostProcessor]):
    tool_post_processor_implementations: Dict[str, Serializer[ToolPostProcessor]] = {}
    
    def to_dict(self, obj: ToolPostProcessor) -> dict:
        return ToolPostProcessorConfigSerializer.tool_post_processor_implementations[obj.tool_post_processor_type].to_dict(obj)
    
    def validate_dict(self, data: dict) -> ToolPostProcessor:
        try:
            return ToolPostProcessorConfigSerializer.tool_post_processor_implementations[data['tool_post_processor_type']].validate_dict(data)
        except KeyError:
            raise ValueError(f"Invalid tool post processor type: {data['tool_post_processor_type']}")
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid ToolPostProcessor: " + traceback.format_exc()) from e
