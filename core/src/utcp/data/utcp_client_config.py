from pydantic import BaseModel, Field, field_serializer, field_validator
from typing import Optional, List, Dict, Union, Any
from utcp.data.variable_loader import VariableLoader, VariableLoaderSerializer
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository, ConcurrentToolRepositoryConfigSerializer
from utcp.interfaces.tool_search_strategy import ToolSearchStrategy, ToolSearchStrategyConfigSerializer
from utcp.data.call_template import CallTemplate, CallTemplateSerializer
from utcp.interfaces.tool_post_processor import ToolPostProcessor, ToolPostProcessorConfigSerializer
import traceback

class UtcpClientConfig(BaseModel):
    """REQUIRED
    Configuration model for UTCP client setup.

    Provides comprehensive configuration options for UTCP clients including
    variable definitions, provider file locations, and variable loading
    mechanisms. Supports hierarchical variable resolution with multiple
    sources.

    Variable Resolution Order:
        1. Direct variables dictionary
        2. Custom variable loaders (in order)
        3. Environment variables

    Attributes:
        variables (Optional[Dict[str, str]]): A dictionary of directly-defined
            variables for substitution.
        load_variables_from (Optional[List[VariableLoader]]): A list of
            variable loader configurations for loading variables from external
            sources like .env files or remote services.
        tool_repository (ConcurrentToolRepository): Configuration for the tool
            repository, which manages the storage and retrieval of tools.
            Defaults to an in-memory repository.
        tool_search_strategy (ToolSearchStrategy): Configuration for the tool
            search strategy, defining how tools are looked up. Defaults to a
            tag and description-based search.
        post_processing (List[ToolPostProcessor]): A list of tool post-processor
            configurations to be applied after a tool call.
        manual_call_templates (List[CallTemplate]): A list of manually defined
            call templates for registering tools that don't have a provider.

    Example:
        ```python
        config = UtcpClientConfig(
            variables={"MANUAL__NAME_API_KEY_NAME": "$REMAPPED_API_KEY"},
            load_variables_from=[
                VariableLoaderSerializer().validate_dict({"variable_loader_type": "dotenv", "env_file_path": ".env"})
            ],
            tool_repository={
                "tool_repository_type": "in_memory"
            },
            tool_search_strategy={
                "tool_search_strategy_type": "tag_and_description_word_match"
            },
            post_processing=[],
            manual_call_templates=[]
        )
        ```
    """
    variables: Optional[Dict[str, str]] = Field(default_factory=dict)
    load_variables_from: Optional[List[VariableLoader]] = None
    tool_repository: ConcurrentToolRepository = Field(default_factory=lambda: ConcurrentToolRepositoryConfigSerializer().validate_dict({"tool_repository_type": ConcurrentToolRepositoryConfigSerializer.default_repository}))
    tool_search_strategy: ToolSearchStrategy = Field(default_factory=lambda: ToolSearchStrategyConfigSerializer().validate_dict({"tool_search_strategy_type": ToolSearchStrategyConfigSerializer.default_strategy}))
    post_processing: List[ToolPostProcessor] = Field(default_factory=list)
    manual_call_templates: List[CallTemplate] = Field(default_factory=list)

    @field_serializer("tool_repository")
    def serialize_tool_repository(self, v: ConcurrentToolRepository):
        return ConcurrentToolRepositoryConfigSerializer().to_dict(v)

    @field_validator("tool_repository", mode="before")
    @classmethod
    def validate_tool_repository(cls, v: Union[ConcurrentToolRepository, dict]):
        if isinstance(v, ConcurrentToolRepository):
            return v
        return ConcurrentToolRepositoryConfigSerializer().validate_dict(v)

    @field_serializer("tool_search_strategy")
    def serialize_tool_search_strategy(self, v: ToolSearchStrategy):
        return ToolSearchStrategyConfigSerializer().to_dict(v)

    @field_validator("tool_search_strategy", mode="before")
    @classmethod
    def validate_tool_search_strategy(cls, v: Union[ToolSearchStrategy, dict]):
        if isinstance(v, ToolSearchStrategy):
            return v
        return ToolSearchStrategyConfigSerializer().validate_dict(v)

    @field_serializer("load_variables_from")
    def serialize_load_variables_from(self, v: Optional[List[VariableLoader]]):
        if v is None:
            return None
        return [VariableLoaderSerializer().to_dict(item) for item in v]
    
    @field_validator("load_variables_from", mode="before")
    @classmethod
    def validate_load_variables_from(cls, v: Optional[List[Union[VariableLoader, dict]]]):
        if v is None:
            return None
        return [item if isinstance(item, VariableLoader) else VariableLoaderSerializer().validate_dict(item) for item in v]

    @field_serializer("manual_call_templates")
    def serialize_manual_call_templates(self, v: List[CallTemplate]):
        return [CallTemplateSerializer().to_dict(v) for v in v]
    
    @field_validator("manual_call_templates", mode="before")
    @classmethod
    def validate_manual_call_templates(cls, v: List[Union[CallTemplate, dict]]):
        return [v if isinstance(v, CallTemplate) else CallTemplateSerializer().validate_dict(v) for v in v]

    @field_serializer("post_processing")
    def serialize_post_processing(self, v: List[ToolPostProcessor]):
        return [ToolPostProcessorConfigSerializer().to_dict(v) for v in v]
    
    @field_validator("post_processing", mode="before")
    @classmethod
    def validate_post_processing(cls, v: List[Union[ToolPostProcessor, dict]]):
        return [v if isinstance(v, ToolPostProcessor) else ToolPostProcessorConfigSerializer().validate_dict(v) for v in v]

class UtcpClientConfigSerializer(Serializer[UtcpClientConfig]):
    """REQUIRED
    Serializer for UTCP client configurations.

    Defines the contract for serializers that convert UTCP client configurations to and from
    dictionaries for storage or transmission. Serializers are responsible for:
    - Converting UTCP client configurations to dictionaries for storage or transmission
    - Converting dictionaries back to UTCP client configurations
    - Ensuring data consistency during serialization and deserialization
    """
    def to_dict(self, obj: UtcpClientConfig) -> dict:
        """REQUIRED
        Convert a UtcpClientConfig object to a dictionary.

        Args:
            obj: The UtcpClientConfig object to convert.

        Returns:
            The dictionary converted from the UtcpClientConfig object.
        """
        return obj.model_dump()
    
    def validate_dict(self, data: dict) -> UtcpClientConfig:
        """REQUIRED
        Validate a dictionary and convert it to a UtcpClientConfig object.

        Args:
            data: The dictionary to validate and convert.

        Returns:
            The UtcpClientConfig object converted from the dictionary.
        """
        try:
            return UtcpClientConfig.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid UtcpClientConfig: " + traceback.format_exc()) from e
