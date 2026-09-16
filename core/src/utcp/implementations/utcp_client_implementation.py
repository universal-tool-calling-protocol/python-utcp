from utcp.data.utcp_manual import UtcpManual

import re
import os
import json
import asyncio
from typing import Callable, Dict, Any, List, Union, Optional, AsyncGenerator, TYPE_CHECKING

from utcp.data.call_template import CallTemplate
from utcp.data.call_template import CallTemplateSerializer
from utcp.data.tool import Tool
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepositoryConfigSerializer, ConcurrentToolRepository
from utcp.interfaces.tool_search_strategy import ToolSearchStrategyConfigSerializer, ToolSearchStrategy
from utcp.interfaces.variable_substitutor import VariableSubstitutor
from utcp.data.utcp_client_config import UtcpClientConfig, UtcpClientConfigSerializer
from utcp.implementations.default_variable_substitutor import DefaultVariableSubstitutor
from utcp.implementations.tag_search import TagAndDescriptionWordMatchStrategy
from utcp.exceptions import UtcpVariableNotFound, UtcpProtocolCloseError
from utcp.data.register_manual_response import RegisterManualResult
from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.exceptions import UtcpSerializerValidationError
import traceback
from utcp.utcp_client import UtcpClient
import logging

logger = logging.getLogger(__name__)

class UtcpClientImplementation(UtcpClient):
    """REQUIRED
    Implementation of the `UtcpClient` interface.

    This class provides a concrete implementation of the `UtcpClient` interface.
    """
    def __init__(
        self,
        config: UtcpClientConfig,
        variable_substitutor: VariableSubstitutor,
        root_dir: str,
    ):
        super().__init__(config, root_dir)
        self.variable_substitutor = variable_substitutor
        # The protocol instances this client CREATED (from the factory registry)
        # and therefore owns: what its teardown closes. They are adopted by
        # `create()` after construction, inside its cleanup guard — a
        # constructor cannot await, so nothing that needs closing on failure is
        # created here. Shared instances stay in the process registry, looked up
        # live, and are never closed on this client's behalf.
        self._owned_comm_protocols: List[CommunicationProtocol] = []
        self._own_comm_protocols_by_type: Dict[str, CommunicationProtocol] = {}

    def _adopt(self, protocol_type: str, factory: Callable[[], CommunicationProtocol]) -> CommunicationProtocol:
        """Create this client's own instance of a protocol and record it as owned.

        Recorded the moment it exists, so a factory that raises part-way
        through a batch leaves the ones before it closable.
        """
        protocol = factory()
        self._owned_comm_protocols.append(protocol)
        self._own_comm_protocols_by_type[protocol_type] = protocol
        return protocol

    def _adopt_factory_protocols(self) -> None:
        """Instantiate this client's own protocols from every factory registered so far."""
        for protocol_type, factory in CommunicationProtocol.communication_protocol_factories.items():
            self._adopt(protocol_type, factory)

    def _protocol_for(self, call_template_type: str) -> CommunicationProtocol:
        """Resolve the protocol this client uses for a call template type.

        In order: this client's own instance; a factory registered since the
        client was created (adopted now, so it is owned and closed like the
        rest); a shared instance. Both registries are consulted live, so a
        type resolves the same way whenever it was registered — and a factory
        wins over a shared instance of the same type, which is what lets a
        plugin migrate from instance to factory without callers changing
        anything.
        """
        protocol = self._own_comm_protocols_by_type.get(call_template_type)
        if protocol is None:
            factory = CommunicationProtocol.communication_protocol_factories.get(call_template_type)
            if factory is not None:
                protocol = self._adopt(call_template_type, factory)
        if protocol is None:
            protocol = CommunicationProtocol.communication_protocols.get(call_template_type)
        if protocol is None:
            available = set(self._own_comm_protocols_by_type) | set(CommunicationProtocol.communication_protocol_factories) | set(CommunicationProtocol.communication_protocols)
            raise ValueError(f"No registered communication protocol of type {call_template_type} found, available types: {sorted(available)}")
        return protocol

    async def _close_owned_protocols(self) -> None:
        """Close every protocol this client created, waiting for all of them even when one fails."""
        results = await asyncio.gather(*(protocol.close() for protocol in self._owned_comm_protocols), return_exceptions=True)
        failures = [result for result in results if isinstance(result, BaseException)]
        if failures:
            raise UtcpProtocolCloseError(failures, len(results))

    async def close(self) -> None:
        """REQUIRED
        Close the protocol instances this client created and release their resources.

        Only what this client created. A shared instance is in use by every
        other client in the process — closing it here would clear their state
        too (a credential cache, a decorator's registry), which is the
        cross-client damage per-client instances exist to prevent. Shared
        instances live as long as the process that registered them.

        Raises:
            UtcpProtocolCloseError: If one or more owned instances failed to close.
                Every instance is still asked to close first.
        """
        await self._close_owned_protocols()
        logger.info("UTCP client closed, with the protocols it owned.")

    @classmethod
    async def create(
        cls,
        root_dir: Optional[str] = None,
        config: Optional[Union[str, Dict[str, Any], UtcpClientConfig]] = None,
    ) -> 'UtcpClient':
        """REQUIRED
        Create a new `UtcpClient` instance.

        Args:
            root_dir: The root directory for the client.
            config: The configuration for the client.

        Returns:
            A new `UtcpClient` instance.
        """
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

        # Everything from here on can fail, and the caller never receives a
        # client it could close — so whatever this client CREATED is closed
        # here before the failure is re-raised. Only what it created: the shared
        # instances are in use by every other client and are not this one's.
        try:
            client._adopt_factory_protocols()

            # Substitute variables in the config
            if client.config.variables:
                config_without_vars = client_config_serializer.copy(client.config)
                config_without_vars.variables = None
                client.config.variables = client.variable_substitutor.substitute(client.config.variables, config_without_vars)

            # Load the manuals if any
            if config.manual_call_templates:
                await client.register_manuals(config.manual_call_templates)
        except BaseException:
            try:
                await client._close_owned_protocols()
            except Exception:
                # The initialization failure stays the error the caller sees;
                # the cleanup failure is reported rather than swallowed, because
                # the caller has no client through which to retry it.
                logger.error("UtcpClient.create failed, and closing the protocols it had created failed too", exc_info=True)
            raise

        return client

    async def register_manual(self, manual_call_template: CallTemplate) -> RegisterManualResult:
        """REQUIRED
        Register a manual in the client.

        Registers a manual and its tools with the client. During registration, tools are
        filtered based on the manual's `allowed_communication_protocols` setting:
        
        - If `allowed_communication_protocols` is set to a non-empty list, only tools using
          protocols in that list are registered.
        - If `allowed_communication_protocols` is None or empty, it defaults to only allowing
          the manual's own `call_template_type`. This provides secure-by-default behavior.
        
        Tools that don't match the allowed protocols are excluded from registration and a
        warning is logged for each excluded tool.

        Args:
            manual_call_template: The `CallTemplate` instance representing the manual to register.

        Returns:
            A `RegisterManualResult` instance containing the registered tools (filtered by
            allowed protocols) and any errors encountered.

        Raises:
            ValueError: If manual name is already registered or communication protocol is not found.
        """
        # Replace all non-word characters with underscore
        manual_call_template.name = re.sub(r'[^\w]', '_', manual_call_template.name)
        if await self.config.tool_repository.get_manual(manual_call_template.name) is not None:
            raise ValueError(f"Manual {manual_call_template.name} already registered, please use a different name or deregister the existing manual")
        manual_call_template = self._substitute_call_template_variables(manual_call_template, manual_call_template.name)

        result = await self._protocol_for(manual_call_template.call_template_type).register_manual(self, manual_call_template)

        if result.success:
            # Determine allowed protocols: use explicit list or default to manual's own protocol
            allowed_protocols = manual_call_template.allowed_communication_protocols
            if not allowed_protocols:
                allowed_protocols = [manual_call_template.call_template_type]
            
            # Filter tools based on allowed communication protocols
            filtered_tools = []
            for tool in result.manual.tools:
                tool_protocol = tool.tool_call_template.call_template_type if tool.tool_call_template else manual_call_template.call_template_type
                if tool_protocol in allowed_protocols:
                    if not tool.name.startswith(manual_call_template.name + "."):
                        tool.name = manual_call_template.name + "." + tool.name
                    filtered_tools.append(tool)
                else:
                    logger.warning(
                        f"Tool '{tool.name}' uses communication protocol '{tool_protocol}' "
                        f"which is not in allowed protocols {allowed_protocols} for manual '{manual_call_template.name}'. "
                        f"Tool will not be registered."
                    )
            
            result.manual.tools = filtered_tools
            await self.config.tool_repository.save_manual(result.manual_call_template, result.manual)

        return result

    async def register_manuals(self, manual_call_templates: List[CallTemplate]) -> List[RegisterManualResult]:
        """REQUIRED
        Register multiple manuals in the client.

        Args:
            manual_call_templates: A list of `CallTemplate` instances representing the manuals to register.

        Returns:
            A list of `RegisterManualResult` instances representing the results of the registration.
        """
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
                        manual=UtcpManual(manual_version="0.0.0", tools=[]),
                        success=False,
                        errors=[traceback.format_exc()]
                    )
            
            tasks.append(try_register_manual())
        
        # Wait for EVERY registration to settle, even when one raises. The
        # caller receives the failure only once no sibling registration is
        # still running underneath it — create(), for one, closes the
        # protocols right after, and a registration still in flight would be
        # using a closed one.
        results = await asyncio.gather(*tasks, return_exceptions=True)
        failures = [result for result in results if isinstance(result, BaseException)]
        if failures:
            raise failures[0]
        return [p for p in results if p is not None]

    async def deregister_manual(self, manual_name: str) -> bool:
        """REQUIRED
        Deregister a manual from the client.

        Args:
            manual_name: The name of the manual to deregister.

        Returns:
            A boolean indicating whether the manual was successfully deregistered.
        """
        manual_call_template = await self.config.tool_repository.get_manual_call_template(manual_name)
        if manual_call_template is None:
            return False
        await self._protocol_for(manual_call_template.call_template_type).deregister_manual(self, manual_call_template)
        return await self.config.tool_repository.remove_manual(manual_name)

    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Any:
        """REQUIRED
        Call a tool in the client.

        Executes a registered tool with the provided arguments. Before execution, validates
        that the tool's communication protocol is allowed by the parent manual's
        `allowed_communication_protocols` setting:
        
        - If `allowed_communication_protocols` is set to a non-empty list, the tool's protocol
          must be in that list.
        - If `allowed_communication_protocols` is None or empty, only tools using the manual's
          own `call_template_type` are allowed.

        Args:
            tool_name: The fully qualified name of the tool (e.g., "manual_name.tool_name").
            tool_args: A dictionary of arguments to pass to the tool.

        Returns:
            The result of the tool call, after any post-processing.

        Raises:
            ValueError: If the tool is not found or if the tool's communication protocol
                is not in the manual's allowed protocols.
        """
        manual_name = tool_name.split(".")[0]
        tool = await self.config.tool_repository.get_tool(tool_name)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")
        tool_call_template = tool.tool_call_template
        tool_call_template = self._substitute_call_template_variables(tool_call_template, manual_name)
        
        # Check if the tool's communication protocol is allowed by the manual
        manual_call_template = await self.config.tool_repository.get_manual_call_template(manual_name)
        if manual_call_template:
            allowed_protocols = manual_call_template.allowed_communication_protocols
            if not allowed_protocols:
                allowed_protocols = [manual_call_template.call_template_type]
            if tool_call_template.call_template_type not in allowed_protocols:
                raise ValueError(
                    f"Tool '{tool_name}' uses communication protocol '{tool_call_template.call_template_type}' "
                    f"which is not allowed by manual '{manual_name}'. "
                    f"Allowed protocols: {allowed_protocols}"
                )
        
        result = await self._protocol_for(tool_call_template.call_template_type).call_tool(self, tool_name, tool_args, tool_call_template)
        
        for post_processor in self.config.post_processing:
            result = post_processor.post_process(self, tool, tool_call_template, result)
        return result

    async def call_tool_streaming(self, tool_name: str, tool_args: Dict[str, Any]) -> AsyncGenerator[Any, None]:
        """REQUIRED
        Call a tool in the client with streaming response.

        Executes a registered tool with streaming output. Before execution, validates
        that the tool's communication protocol is allowed by the parent manual's
        `allowed_communication_protocols` setting:
        
        - If `allowed_communication_protocols` is set to a non-empty list, the tool's protocol
          must be in that list.
        - If `allowed_communication_protocols` is None or empty, only tools using the manual's
          own `call_template_type` are allowed.

        Args:
            tool_name: The fully qualified name of the tool (e.g., "manual_name.tool_name").
            tool_args: A dictionary of arguments to pass to the tool.

        Yields:
            Chunks of the tool's streaming response, after any post-processing.

        Raises:
            ValueError: If the tool is not found or if the tool's communication protocol
                is not in the manual's allowed protocols.
        """
        manual_name = tool_name.split(".")[0]
        tool = await self.config.tool_repository.get_tool(tool_name)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")
        tool_call_template = tool.tool_call_template
        tool_call_template = self._substitute_call_template_variables(tool_call_template, manual_name)
        
        # Check if the tool's communication protocol is allowed by the manual
        manual_call_template = await self.config.tool_repository.get_manual_call_template(manual_name)
        if manual_call_template:
            allowed_protocols = manual_call_template.allowed_communication_protocols
            if not allowed_protocols:
                allowed_protocols = [manual_call_template.call_template_type]
            if tool_call_template.call_template_type not in allowed_protocols:
                raise ValueError(
                    f"Tool '{tool_name}' uses communication protocol '{tool_call_template.call_template_type}' "
                    f"which is not allowed by manual '{manual_name}'. "
                    f"Allowed protocols: {allowed_protocols}"
                )
        
        async for item in self._protocol_for(tool_call_template.call_template_type).call_tool_streaming(self, tool_name, tool_args, tool_call_template):
            for post_processor in self.config.post_processing:
                item = post_processor.post_process(self, tool, tool_call_template, item)
            yield item

    async def search_tools(self, query: str, limit: int = 10, any_of_tags_required: Optional[List[str]] = None) -> List[Tool]:
        """REQUIRED
        Search for tools based on the given query.

        Args:
            query: The query to search for.
            limit: The maximum number of results to return.
            any_of_tags_required: A list of tags that must be present in the tool.

        Returns:
            A list of tools that match the query.
        """
        return await self.config.tool_search_strategy.search_tools(
            tool_repository=self.config.tool_repository,
            query=query,
            limit=limit,
            any_of_tags_required=any_of_tags_required,
        )

    async def get_required_variables_for_manual_and_tools(self, manual_call_template: CallTemplate) -> List[str]:
        """REQUIRED
        Get the required variables for a manual and its tools.

        Args:
            manual_call_template: The `CallTemplate` instance representing the manual.

        Returns:
            A list of required variables for the manual and its tools.
        """
        manual_call_template.name = re.sub(r'[^\w]', '_', manual_call_template.name)
        variables_for_CallTemplate = self.variable_substitutor.find_required_variables(CallTemplateSerializer().to_dict(manual_call_template), manual_call_template.name)
        if len(variables_for_CallTemplate) > 0:
            try:
                manual_call_template = self._substitute_call_template_variables(manual_call_template, manual_call_template.name)
            except UtcpVariableNotFound as e:
                return variables_for_CallTemplate
            return variables_for_CallTemplate
        register_manual_result: RegisterManualResult = await self._protocol_for(manual_call_template.call_template_type).register_manual(self, manual_call_template)
        for tool in register_manual_result.manual.tools:
            variables_for_CallTemplate.extend(self.variable_substitutor.find_required_variables(CallTemplateSerializer().to_dict(tool.tool_call_template), manual_call_template.name))
        return variables_for_CallTemplate

    async def get_required_variables_for_registered_tool(self, tool_name: str) -> List[str]:
        """REQUIRED
        Get the required variables for a registered tool.

        Args:
            tool_name: The name of the tool.

        Returns:
            A list of required variables for the tool.
        """
        manual_name = tool_name.split(".")[0]
        tool = await self.config.tool_repository.get_tool(tool_name)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")
        return self.variable_substitutor.find_required_variables(CallTemplateSerializer().to_dict(tool.tool_call_template), manual_name)

    def _substitute_call_template_variables(self, call_template: CallTemplate, namespace: Optional[str] = None) -> CallTemplate:
        call_template_dict = CallTemplateSerializer().to_dict(call_template)
        processed_dict = self.variable_substitutor.substitute(call_template_dict, self.config, namespace)
        return CallTemplateSerializer().validate_dict(processed_dict)
