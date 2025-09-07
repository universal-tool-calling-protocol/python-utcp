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
    """REQUIRED
    Post-processor that filters dictionary keys from tool results.

    Provides flexible filtering capabilities to include or exclude specific keys
    from dictionary results, with support for nested dictionaries and lists.
    Can be configured to apply filtering only to specific tools or manuals.

    Attributes:
        tool_post_processor_type: Always "filter_dict" for this processor.
        exclude_keys: List of keys to remove from dictionary results.
        only_include_keys: List of keys to keep in dictionary results (all others removed).
        exclude_tools: List of tool names to skip processing for.
        only_include_tools: List of tool names to process (all others skipped).
        exclude_manuals: List of manual names to skip processing for.
        only_include_manuals: List of manual names to process (all others skipped).
    """
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
        if self.exclude_keys:
            result = self._filter_dict_exclude_keys(result)
        if self.only_include_keys:
            result = self._filter_dict_only_include_keys(result)
        return result

    def _filter_dict_exclude_keys(self, result: Any) -> Any:
        if isinstance(result, dict):
            new_result = {}
            for key, value in result.items():
                if key not in self.exclude_keys:
                    new_result[key] = self._filter_dict_exclude_keys(value)
            return new_result

        if isinstance(result, list):
            new_list = []
            for item in result:
                processed_item = self._filter_dict_exclude_keys(item)
                if isinstance(processed_item, dict):
                    if processed_item:
                        new_list.append(processed_item)
                elif isinstance(processed_item, list):
                    if processed_item:
                        new_list.append(processed_item)
                else:
                    new_list.append(processed_item)
            return new_list

        return result
    
    def _filter_dict_only_include_keys(self, result: Any) -> Any:
        if isinstance(result, dict):
            new_result = {}
            for key, value in result.items():
                if key in self.only_include_keys:
                    if isinstance(value, dict):
                        new_result[key] = self._filter_dict_only_include_keys(value)
                    else:
                        new_result[key] = value
                else:
                    processed_value = self._filter_dict_only_include_keys(value)
                    if (isinstance(processed_value, dict) and processed_value) or \
                    (isinstance(processed_value, list) and processed_value):
                        new_result[key] = processed_value
            return new_result

        if isinstance(result, list):
            new_list = []
            for item in result:
                processed_item = self._filter_dict_only_include_keys(item)
                if isinstance(processed_item, dict) and processed_item:
                    new_list.append(processed_item)
                if isinstance(processed_item, list) and processed_item:
                    new_list.append(processed_item)
            return new_list

        return result

class FilterDictPostProcessorConfigSerializer(Serializer[FilterDictPostProcessor]):
    """REQUIRED
    Serializer for FilterDictPostProcessor configuration."""
    def to_dict(self, obj: FilterDictPostProcessor) -> dict:
        return obj.model_dump()
    
    def validate_dict(self, data: dict) -> FilterDictPostProcessor:
        try:
            return FilterDictPostProcessor.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid FilterDictPostProcessor: " + traceback.format_exc()) from e
