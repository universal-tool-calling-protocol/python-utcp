from utcp.interfaces.tool_post_processor import ToolPostProcessor
from utcp.data.tool import Tool
from utcp.data.call_template import CallTemplate
from typing import Any, List, Optional, TYPE_CHECKING, Literal
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

if TYPE_CHECKING:
    from utcp.utcp_client import UtcpClient

class LimitStringsPostProcessor(ToolPostProcessor):
    tool_post_processor_type: Literal["limit_strings"] = "limit_strings"
    limit: int = 10000
    exclude_tools: Optional[List[str]] = None
    only_include_tools: Optional[List[str]] = None
    exclude_manuals: Optional[List[str]] = None
    only_include_manuals: Optional[List[str]] = None

    def post_process(self, caller: 'UtcpClient', tool: Tool, manual_call_template: 'CallTemplate', result: Any) -> Any:
        if self.exclude_tools and tool.name in self.exclude_tools:
            return result
        if self.only_include_tools and tool.name not in self.only_include_tools:
            return result
        if self.exclude_manuals and manual_call_template.name in self.exclude_manuals:
            return result
        if self.only_include_manuals and manual_call_template.name not in self.only_include_manuals:
            return result

        return self._process_object(result)

    def _process_object(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return obj[:self.limit]
        if isinstance(obj, list):
            return [self._process_object(item) for item in obj]
        if isinstance(obj, dict):
            return {key: self._process_object(value) for key, value in obj.items()}
        return obj

class LimitStringsPostProcessorConfigSerializer(Serializer[LimitStringsPostProcessor]):
    def to_dict(self, obj: LimitStringsPostProcessor) -> dict:
        return obj.model_dump()
    
    def validate_dict(self, data: dict) -> LimitStringsPostProcessor:
        try:
            return LimitStringsPostProcessor.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid LimitStringsPostProcessor: " + traceback.format_exc()) from e
