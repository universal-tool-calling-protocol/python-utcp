"""
File communication protocol for UTCP client.

This protocol reads UTCP manuals (or OpenAPI specs) from local files to register
tools. It does not maintain any persistent connections.
For direct text content, use the text protocol instead.
"""
import json
import yaml
import aiofiles
from pathlib import Path
from typing import Dict, Any, AsyncGenerator, TYPE_CHECKING

from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplate
from utcp.data.utcp_manual import UtcpManual, UtcpManualSerializer
from utcp.data.register_manual_response import RegisterManualResult
from utcp_http.openapi_converter import OpenApiConverter
from utcp_file.file_call_template import FileCallTemplate
import traceback

if TYPE_CHECKING:
    from utcp.utcp_client import UtcpClient

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
)

logger = logging.getLogger(__name__)


class FileCommunicationProtocol(CommunicationProtocol):
    """REQUIRED
    Communication protocol for file-based UTCP manuals and tools."""

    def _log_info(self, message: str) -> None:
        logger.info(f"[FileCommunicationProtocol] {message}")

    def _log_error(self, message: str) -> None:
        logger.error(f"[FileCommunicationProtocol Error] {message}")

    async def register_manual(self, caller: 'UtcpClient', manual_call_template: CallTemplate) -> RegisterManualResult:
        """REQUIRED
        Register a file manual and return its tools as a UtcpManual."""
        if not isinstance(manual_call_template, FileCallTemplate):
            raise ValueError("FileCommunicationProtocol requires a FileCallTemplate")

        file_path = Path(manual_call_template.file_path)
        if not file_path.is_absolute() and caller.root_dir:
            file_path = Path(caller.root_dir) / file_path

        self._log_info(f"Reading manual from '{file_path}'")

        try:
            if not file_path.exists():
                raise FileNotFoundError(f"Manual file not found: {file_path}")

            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                file_content = await f.read()

            # Parse based on extension
            data: Any
            if file_path.suffix.lower() in [".yaml", ".yml"]:
                data = yaml.safe_load(file_content)
            else:
                data = json.loads(file_content)

            utcp_manual: UtcpManual
            if isinstance(data, dict) and ("openapi" in data or "swagger" in data or "paths" in data):
                self._log_info("Detected OpenAPI specification. Converting to UTCP manual.")
                converter = OpenApiConverter(
                    data,
                    spec_url=file_path.as_uri(),
                    call_template_name=manual_call_template.name,
                    auth_tools=manual_call_template.auth_tools
                )
                utcp_manual = converter.convert()
            else:
                # Try to validate as UTCP manual directly
                utcp_manual = UtcpManualSerializer().validate_dict(data)

            self._log_info(f"Loaded {len(utcp_manual.tools)} tools from '{file_path}'")
            return RegisterManualResult(
                manual_call_template=manual_call_template,
                manual=utcp_manual,
                success=True,
                errors=[],
            )

        except (json.JSONDecodeError, yaml.YAMLError) as e:
            self._log_error(f"Failed to parse manual '{file_path}': {traceback.format_exc()}")
            return RegisterManualResult(
                manual_call_template=manual_call_template,
                manual=UtcpManual(tools=[]),
                success=False,
                errors=[traceback.format_exc()],
            )
        except Exception as e:
            self._log_error(f"Unexpected error reading manual '{file_path}': {traceback.format_exc()}")
            return RegisterManualResult(
                manual_call_template=manual_call_template,
                manual=UtcpManual(tools=[]),
                success=False,
                errors=[traceback.format_exc()],
            )

    async def deregister_manual(self, caller: 'UtcpClient', manual_call_template: CallTemplate) -> None:
        """REQUIRED
        Deregister a file manual (no-op)."""
        if isinstance(manual_call_template, FileCallTemplate):
            self._log_info(f"Deregistering file manual '{manual_call_template.name}' (no-op)")

    async def call_tool(self, caller: 'UtcpClient', tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        """REQUIRED
        Call a tool: for file templates, return file content from the configured path."""
        if not isinstance(tool_call_template, FileCallTemplate):
            raise ValueError("FileCommunicationProtocol requires a FileCallTemplate for tool calls")

        file_path = Path(tool_call_template.file_path)
        if not file_path.is_absolute() and caller.root_dir:
            file_path = Path(caller.root_dir) / file_path

        self._log_info(f"Reading content from '{file_path}' for tool '{tool_name}'")

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
            return content
        except FileNotFoundError:
            self._log_error(f"File not found for tool '{tool_name}': {file_path}")
            raise

    async def call_tool_streaming(self, caller: 'UtcpClient', tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any, None]:
        """REQUIRED
        Streaming variant: yields the full content as a single chunk."""
        result = await self.call_tool(caller, tool_name, tool_args, tool_call_template)
        yield result
