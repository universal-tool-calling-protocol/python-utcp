from pydantic import BaseModel, Field, field_serializer, field_validator
from typing import Optional, List, Dict, Union
from utcp.data.variable_loader import VariableLoader, VariableLoaderSerializer
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository
from utcp.interfaces.tool_search_strategy import ToolSearchStrategy
from utcp.data.call_template import CallTemplate, CallTemplateSerializer

class UtcpClientConfig(BaseModel):
    """Configuration model for UTCP client setup.

    Provides comprehensive configuration options for UTCP clients including
    variable definitions, provider file locations, and variable loading
    mechanisms. Supports hierarchical variable resolution with multiple
    sources.

    Variable Resolution Order:
        1. Direct variables dictionary
        2. Custom variable loaders (in order)
        3. Environment variables

    Attributes:
        variables: Direct variable definitions as key-value pairs.
            These take precedence over other variable sources.
        providers_file_path: Optional path to a file containing provider
            configurations. Supports JSON and YAML formats.
        load_variables_from: List of variable loaders to use for
            variable resolution. Loaders are consulted in order.

    Example:
        ```python
        config = UtcpClientConfig(
            variables={"MANUAL__NAME_API_KEY_NAME": "$REMAPPED_API_KEY"},
            load_variables_from=[
                VariableLoaderSerializer().validate_dict({"type": "dotenv", "env_file_path": ".env"})
            ],
            tool_repository="in_memory",
            tool_search_strategy="tag_and_description_word_match",
            manual_call_templates=[]
        )
        ```
    """
    variables: Optional[Dict[str, str]] = Field(default_factory=dict)
    load_variables_from: Optional[List[VariableLoader]] = None
    tool_repository: str = ConcurrentToolRepository.default_repository
    tool_search_strategy: str = ToolSearchStrategy.default_strategy
    manual_call_templates: List[CallTemplate] = []

    @field_serializer("load_variables_from")
    def serialize_load_variables_from(cls, v: List[VariableLoader]):
        return [VariableLoaderSerializer().to_dict(v) for v in v]
    
    @field_validator("load_variables_from")
    @classmethod
    def validate_load_variables_from(cls, v: List[Union[VariableLoader, dict]]):
        return [v if isinstance(v, VariableLoader) else VariableLoaderSerializer().validate_dict(v) for v in v]

    @field_serializer("manual_call_templates")
    def serialize_manual_call_templates(cls, v: List[CallTemplate]):
        return [CallTemplateSerializer().to_dict(v) for v in v]
    
    @field_validator("manual_call_templates")
    @classmethod
    def validate_manual_call_templates(cls, v: List[Union[CallTemplate, dict]]):
        return [v if isinstance(v, CallTemplate) else CallTemplateSerializer().validate_dict(v) for v in v]

class UtcpClientConfigSerializer(Serializer[UtcpClientConfig]):
    def to_dict(self, obj: UtcpClientConfig) -> dict:
        return obj.model_dump()
    
    def validate_dict(self, data: dict) -> UtcpClientConfig:
        try:
            return UtcpClientConfig.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid UtcpClientConfig: " + str(e))
