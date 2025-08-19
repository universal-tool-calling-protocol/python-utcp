from utcp.data.utcp_manual import UtcpManual

import re
import os
import json
import asyncio
from typing import Dict, Any, List, Union, Optional, AsyncGenerator, TYPE_CHECKING

from utcp.data.call_template import CallTemplate
from utcp.data.call_template import CallTemplateSerializer
from utcp.data.tool import Tool
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepositoryConfigSerializer, ConcurrentToolRepository
from utcp.interfaces.tool_search_strategy import ToolSearchStrategyConfigSerializer, ToolSearchStrategy
from utcp.interfaces.variable_substitutor import VariableSubstitutor
from utcp.data.utcp_client_config import UtcpClientConfig, UtcpClientConfigSerializer
from utcp.implementations.default_variable_substitutor import DefaultVariableSubstitutor
from utcp.implementations.tag_search import TagAndDescriptionWordMatchStrategy
from utcp.exceptions import UtcpVariableNotFound
from utcp.data.register_manual_response import RegisterManualResult
from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.exceptions import UtcpSerializerValidationError
import traceback
from utcp.utcp_client import UtcpClient
import logging

logger = logging.getLogger(__name__)

class UtcpClientImplementation(UtcpClient):
    def __init__(
        self,
        config: UtcpClientConfig,
        variable_substitutor: VariableSubstitutor,
        root_dir: str,
    ):
        super().__init__(config, root_dir)
        self.variable_substitutor = variable_substitutor

    @classmethod
    async def create(
        cls,
        root_dir: Optional[str] = None,
        config: Optional[Union[str, Dict[str, Any], UtcpClientConfig]] = None,
    ) -> 'UtcpClient':
        # Validate and load the config
        client_config_serializer = UtcpClientConfigSerializer()
        if config is None:
            config = UtcpClientConfig()
        elif isinstance(config, dict):
            config = client_config_serializer.validate_dict(config)
        elif isinstance(config, str):
            try:
                with open(config, "r") as f:
                    file_content = f.read()
                    config = client_config_serializer.validate_dict(json.loads(file_content))
            except UtcpSerializerValidationError as e:
                raise e
            except Exception as e:
                raise ValueError(f"Invalid config file: {config}, error: {traceback.format_exc()}") from e

        # Set the root directory
        if root_dir is None:
            root_dir = os.getcwd()

        # Create the client
        client = cls(config, DefaultVariableSubstitutor(), root_dir)

        # Substitute variables in the config
        if client.config.variables:
            config_without_vars = client_config_serializer.copy(client.config)
            config_without_vars.variables = None
            client.config.variables = client.variable_substitutor.substitute(client.config.variables, config_without_vars)

        # Load the manuals if any
        if config.manual_call_templates:
            await client.register_manuals(config.manual_call_templates)
        
        return client

    async def register_manual(self, manual_call_template: CallTemplate) -> RegisterManualResult:
        # Replace all non-word characters with underscore
        manual_call_template.name = re.sub(r'[^\w]', '_', manual_call_template.name)
        if await self.config.tool_repository.get_manual(manual_call_template.name) is not None:
            raise ValueError(f"Manual {manual_call_template.name} already registered, please use a different name or deregister the existing manual")
        manual_call_template = self._substitute_call_template_variables(manual_call_template, manual_call_template.name)
        if manual_call_template.call_template_type not in CommunicationProtocol.communication_protocols:
            raise ValueError(f"No registered communication protocol of type {manual_call_template.call_template_type} found, available types: {CommunicationProtocol.communication_protocols.keys()}")
        
        result = await CommunicationProtocol.communication_protocols[manual_call_template.call_template_type].register_manual(self, manual_call_template)
        
        if result.success:
            for tool in result.manual.tools:
                if not tool.name.startswith(manual_call_template.name + "."):
                    tool.name = manual_call_template.name + "." + tool.name
            await self.config.tool_repository.save_manual(result.manual_call_template, result.manual)

        return result

    async def register_manuals(self, manual_call_templates: List[CallTemplate]) -> List[RegisterManualResult]:
        # Create tasks for parallel CallTemplate registration
        tasks = []
        for manual_call_template in manual_call_templates:
            async def try_register_manual(manual_call_template=manual_call_template):
                try:
                    result = await self.register_manual(manual_call_template)
                    if result.success:
                        logger.info(f"Successfully registered manual '{manual_call_template.name}' with {len(result.manual.tools)} tools")
                    else:
                        logger.error(f"Error registering manual '{manual_call_template.name}': {result.errors}")
                    return result
                except UtcpVariableNotFound as e:
                    raise e
                except Exception as e:
                    logger.error(f"Error registering manual '{manual_call_template.name}': {traceback.format_exc()}")
                    return RegisterManualResult(
                        manual_call_template=manual_call_template,
                        manual=UtcpManual(utcp_version="1.0.0", manual_version="0.0.0", tools=[]),
                        success=False,
                        errors=[traceback.format_exc()]
                    )
            
            tasks.append(try_register_manual())
        
        # Wait for all tasks to complete and collect results
        results = await asyncio.gather(*tasks)
        return [p for p in results if p is not None]

    async def deregister_manual(self, manual_name: str) -> bool:
        manual_call_template = await self.config.tool_repository.get_manual_call_template(manual_name)
        if manual_call_template is None:
            return False
        await CommunicationProtocol.communication_protocols[manual_call_template.call_template_type].deregister_manual(self, manual_call_template)
        return await self.config.tool_repository.remove_manual(manual_name)

    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Any:
        manual_name = tool_name.split(".")[0]
        tool = await self.config.tool_repository.get_tool(tool_name)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")
        tool_call_template = tool.tool_call_template
        tool_call_template = self._substitute_call_template_variables(tool_call_template, manual_name)
        result = await CommunicationProtocol.communication_protocols[tool_call_template.call_template_type].call_tool(self, tool_name, tool_args, tool_call_template)
        
        for post_processor in self.config.post_processing:
            result = post_processor.post_process(self, tool, tool_call_template, result)
        return result

    async def call_tool_streaming(self, tool_name: str, tool_args: Dict[str, Any]) -> AsyncGenerator[Any, None]:
        manual_name = tool_name.split(".")[0]
        tool = await self.config.tool_repository.get_tool(tool_name)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")
        tool_call_template = tool.tool_call_template
        tool_call_template = self._substitute_call_template_variables(tool_call_template, manual_name)
        async for item in CommunicationProtocol.communication_protocols[tool_call_template.call_template_type].call_tool_streaming(self, tool_name, tool_args, tool_call_template):
            for post_processor in self.config.post_processing:
                item = post_processor.post_process(self, tool, tool_call_template, item)
            yield item

    async def search_tools(self, query: str, limit: int = 10, any_of_tags_required: Optional[List[str]] = None) -> List[Tool]:
        return await self.config.tool_search_strategy.search_tools(
            tool_repository=self.config.tool_repository,
            query=query,
            limit=limit,
            any_of_tags_required=any_of_tags_required,
        )

    async def get_required_variables_for_manual_and_tools(self, manual_call_template: CallTemplate) -> List[str]:
        manual_call_template.name = re.sub(r'[^\w]', '_', manual_call_template.name)
        variables_for_CallTemplate = self.variable_substitutor.find_required_variables(CallTemplateSerializer().to_dict(manual_call_template), manual_call_template.name)
        if len(variables_for_CallTemplate) > 0:
            try:
                manual_call_template = self._substitute_call_template_variables(manual_call_template, manual_call_template.name)
            except UtcpVariableNotFound as e:
                return variables_for_CallTemplate
            return variables_for_CallTemplate
        if manual_call_template.call_template_type not in CommunicationProtocol.communication_protocols:
            raise ValueError(f"CallTemplate type not supported: {manual_call_template.call_template_type}")
        register_manual_result: RegisterManualResult = await CommunicationProtocol.communication_protocols[manual_call_template.call_template_type].register_manual(self, manual_call_template)
        for tool in register_manual_result.manual.tools:
            variables_for_CallTemplate.extend(self.variable_substitutor.find_required_variables(CallTemplateSerializer().to_dict(tool.tool_call_template), manual_call_template.name))
        return variables_for_CallTemplate

    async def get_required_variables_for_registered_tool(self, tool_name: str) -> List[str]:
        manual_name = tool_name.split(".")[0]
        tool = await self.config.tool_repository.get_tool(tool_name)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")
        return self.variable_substitutor.find_required_variables(CallTemplateSerializer().to_dict(tool.tool_call_template), manual_name)

    def _substitute_call_template_variables(self, call_template: CallTemplate, namespace: Optional[str] = None) -> CallTemplate:
        call_template_dict = CallTemplateSerializer().to_dict(call_template)
        processed_dict = self.variable_substitutor.substitute(call_template_dict, self.config, namespace)
        return CallTemplateSerializer().validate_dict(processed_dict)
