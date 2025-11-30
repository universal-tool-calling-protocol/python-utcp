"""
Text communication protocol for UTCP client.

This protocol parses UTCP manuals (or OpenAPI specs) from direct text content.
It's browser-compatible and requires no file system access.
For file-based manuals, use the file protocol instead.
"""
import json
import yaml
from typing import Dict, Any, AsyncGenerator, TYPE_CHECKING

from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplate
from utcp.data.utcp_manual import UtcpManual, UtcpManualSerializer
from utcp.data.register_manual_response import RegisterManualResult
from utcp_http.openapi_converter import OpenApiConverter
from utcp_text.text_call_template import TextCallTemplate
import traceback

if TYPE_CHECKING:
    from utcp.utcp_client import UtcpClient

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
)

logger = logging.getLogger(__name__)


class TextCommunicationProtocol(CommunicationProtocol):
    """REQUIRED
    Communication protocol for text-based UTCP manuals and tools."""

    def _log_info(self, message: str) -> None:
        logger.info(f"[TextCommunicationProtocol] {message}")

    def _log_error(self, message: str) -> None:
        logger.error(f"[TextCommunicationProtocol Error] {message}")

    async def register_manual(self, caller: 'UtcpClient', manual_call_template: CallTemplate) -> RegisterManualResult:
        """REQUIRED
        Register a text manual and return its tools as a UtcpManual."""
        if not isinstance(manual_call_template, TextCallTemplate):
            raise ValueError("TextCommunicationProtocol requires a TextCallTemplate")

        try:
            self._log_info("Parsing direct content for manual")
            content = manual_call_template.content

            # Try JSON first, then YAML
            data: Any
            try:
                data = json.loads(content)
            except json.JSONDecodeError as json_error:
                try:
                    data = yaml.safe_load(content)
                except yaml.YAMLError:
                    raise ValueError(f"Failed to parse content as JSON or YAML: {json_error}")

            utcp_manual: UtcpManual
            if isinstance(data, dict) and ("openapi" in data or "swagger" in data or "paths" in data):
                self._log_info("Detected OpenAPI specification. Converting to UTCP manual.")
                converter = OpenApiConverter(
                    data,
                    spec_url="text://content",
                    call_template_name=manual_call_template.name,
                    auth_tools=manual_call_template.auth_tools,
                    base_url=manual_call_template.base_url
                )
                utcp_manual = converter.convert()
            else:
                # Try to validate as UTCP manual directly
                self._log_info("Validating content as UTCP manual.")
                utcp_manual = UtcpManualSerializer().validate_dict(data)

            self._log_info(f"Successfully registered manual with {len(utcp_manual.tools)} tools.")
            return RegisterManualResult(
                manual_call_template=manual_call_template,
                manual=utcp_manual,
                success=True,
                errors=[],
            )

        except Exception as e:
            err_msg = f"Failed to register text manual: {str(e)}"
            self._log_error(err_msg)
            return RegisterManualResult(
                manual_call_template=manual_call_template,
                manual=UtcpManual(tools=[]),
                success=False,
                errors=[err_msg],
            )

    async def deregister_manual(self, caller: 'UtcpClient', manual_call_template: CallTemplate) -> None:
        """REQUIRED
        Deregister a text manual (no-op)."""
        if isinstance(manual_call_template, TextCallTemplate):
            self._log_info(f"Deregistering text manual '{manual_call_template.name}' (no-op)")

    async def call_tool(self, caller: 'UtcpClient', tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        """REQUIRED
        Execute a tool call. Text protocol returns the content directly."""
        if not isinstance(tool_call_template, TextCallTemplate):
            raise ValueError("TextCommunicationProtocol requires a TextCallTemplate for tool calls")

        self._log_info(f"Returning direct content for tool '{tool_name}'")
        return tool_call_template.content

    async def call_tool_streaming(self, caller: 'UtcpClient', tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any, None]:
        """REQUIRED
        Streaming variant: yields the full content as a single chunk."""
        result = await self.call_tool(caller, tool_name, tool_args, tool_call_template)
        yield result
