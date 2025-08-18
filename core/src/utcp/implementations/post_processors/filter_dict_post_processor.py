from utcp.interfaces.tool_post_processor import ToolPostProcessor
from utcp.data.tool import Tool
from utcp.data.call_template import CallTemplate
from typing import Any, List, Optional, TYPE_CHECKING, Literal
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

if TYPE_CHECKING:
    from utcp.utcp_client import UtcpClient

class FilterDictPostProcessor(ToolPostProcessor):
    tool_post_processor_type: Literal["filter_dict"] = "filter_dict"
    exclude_keys: Optional[List[str]] = None
    only_include_keys: Optional[List[str]] = None
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

        if not self.exclude_keys and not self.only_include_keys:
            return result
        return self._filter_dict(result)

    def _filter_dict(self, result: Any) -> Any:
        if isinstance(result, dict):
            new_result = {}
            if self.exclude_keys:
                for key, value in result.items():
                    if key not in self.exclude_keys:
                        new_result[key] = self._filter_dict(value)
                return new_result
            
            if self.only_include_keys:
                for key, value in result.items():
                    if key in self.only_include_keys:
                        new_result[key] = self._filter_dict(value)
                    else:
                        # If the key is not in the include list, we still want to check its children
                        processed_value = self._filter_dict(value)
                        # Add the child back if it's a non-empty dictionary or a non-empty list after filtering
                        if (isinstance(processed_value, dict) and processed_value) or \
                           (isinstance(processed_value, list) and processed_value):
                            new_result[key] = processed_value
                return new_result

            return {key: self._filter_dict(value) for key, value in result.items()}

        if isinstance(result, list):
            new_list = []
            for item in result:
                processed_item = self._filter_dict(item)
                # Filter out empty dicts and lists, but keep other falsy values like 0, False, etc.
                if isinstance(processed_item, dict) and processed_item:
                    new_list.append(processed_item)
                if isinstance(processed_item, list) and processed_item:
                    new_list.append(processed_item)
            return new_list

        return result

class FilterDictPostProcessorConfigSerializer(Serializer[FilterDictPostProcessor]):
    def to_dict(self, obj: FilterDictPostProcessor) -> dict:
        return obj.model_dump()
    
    def validate_dict(self, data: dict) -> FilterDictPostProcessor:
        try:
            return FilterDictPostProcessor.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid FilterDictPostProcessor: " + traceback.format_exc()) from e
