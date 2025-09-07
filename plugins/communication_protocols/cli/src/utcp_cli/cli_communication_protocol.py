"""Command Line Interface (CLI) communication protocol for the UTCP client.

This module provides an implementation of the `CommunicationProtocol` interface
that enables the UTCP client to interact with command-line tools. It supports
discovering tools by executing a command and parsing its output for a UTCP
manual, as well as calling those tools with arguments.

Key Features:
    - Asynchronous execution of shell commands.
    - Tool discovery by running a command that outputs a UTCP manual.
    - Flexible argument formatting for different CLI conventions.
    - Support for environment variables and custom working directories.
    - Automatic parsing of JSON output with a fallback to raw text.
    - Cross-platform command parsing for Windows and Unix-like systems.

Security Considerations:
    Executing arbitrary command-line tools can be dangerous. This protocol
    should only be used with trusted tools.
"""
import asyncio
import json
import os
import shlex
import sys
from typing import Dict, Any, List, Optional, Callable, AsyncGenerator

from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplate, CallTemplateSerializer
from utcp.data.tool import Tool
from utcp.data.utcp_manual import UtcpManual, UtcpManualSerializer
from utcp.data.register_manual_response import RegisterManualResult
from utcp_cli.cli_call_template import CliCallTemplate, CliCallTemplateSerializer
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
)

logger = logging.getLogger(__name__)

class CliCommunicationProtocol(CommunicationProtocol):
    """REQUIRED
    Communication protocol for interacting with CLI-based tool providers.

    This class implements the `CommunicationProtocol` interface to handle
    communication with command-line tools. It discovers tools by executing a
    command specified in a `CliCallTemplate` and parsing the output for a UTCP
    manual. It also executes tool calls by running the corresponding command
    with the provided arguments.
    """
    
    def __init__(self):
        """Initializes the `CliCommunicationProtocol`."""
    
    def _log_info(self, message: str):
        """Log informational messages."""
        logger.info(f"[CliCommunicationProtocol] {message}")
        
    def _log_error(self, message: str):
        """Log error messages."""
        logger.error(f"[CliCommunicationProtocol Error] {message}")
    
    def _prepare_environment(self, provider: CliCallTemplate) -> Dict[str, str]:
        """Prepare environment variables for command execution.
        
        Args:
            provider: The CLI provider
            
        Returns:
            Environment variables dictionary
        """
        import os
        env = os.environ.copy()
        
        # Add custom environment variables if provided
        if provider.env_vars:
            env.update(provider.env_vars)
        
        return env
    
    async def _execute_command(
        self,
        command: List[str],
        env: Dict[str, str],
        timeout: float = 30.0,
        input_data: Optional[str] = None,
        working_dir: Optional[str] = None
    ) -> tuple[str, str, int]:
        """Execute a command asynchronously.

        Args:
            command: Command and arguments to execute
            env: Environment variables
            timeout: Timeout in seconds
            input_data: Optional input data to pass to the command
            working_dir: Working directory for command execution
            
        Returns:
            Tuple of (stdout, stderr, return_code)
        """
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=working_dir,
                stdin=asyncio.subprocess.PIPE if input_data else None
            )
            
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=input_data.encode('utf-8') if input_data else None),
                timeout=timeout
            )
            
            stdout = stdout_bytes.decode('utf-8', errors='replace')
            stderr = stderr_bytes.decode('utf-8', errors='replace')
            
            return stdout, stderr, process.returncode or 0
            
        except asyncio.TimeoutError:
            # Kill the process if it times out
            if process:
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass  # Process already terminated
            self._log_error(f"Command timed out after {timeout} seconds: {' '.join(command)}")
            raise
        except Exception as e:
            # Ensure process is cleaned up on any error
            if process:
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass  # Process already terminated
            self._log_error(f"Error executing command {' '.join(command)}: {e}")
            raise
    
    async def register_manual(self, caller, manual_call_template: CallTemplate) -> RegisterManualResult:
        """REQUIRED
        Registers a CLI-based manual and discovers its tools.

        This method executes the command specified in the `CliCallTemplate`'s
        `command_name` field. It then attempts to parse the command's output
        (stdout) as a UTCP manual in JSON format.

        Args:
            caller: The UTCP client instance that is calling this method.
            manual_call_template: The `CliCallTemplate` containing the details for
                tool discovery, such as the command to run.

        Returns:
            A `RegisterManualResult` object indicating whether the registration
            was successful and containing the discovered tools.

        Raises:
            ValueError: If the `manual_call_template` is not an instance of
                `CliCallTemplate` or if `command_name` is not set.
        """
        if not isinstance(manual_call_template, CliCallTemplate):
            raise ValueError("CliCommunicationProtocol can only be used with CliCallTemplate")

        if not manual_call_template.command_name:
            raise ValueError(f"CliCallTemplate '{manual_call_template.name}' must have command_name set")

        self._log_info(
            f"Registering CLI manual '{manual_call_template.name}' with command '{manual_call_template.command_name}'"
        )

        try:
            env = self._prepare_environment(manual_call_template)
            # Parse command string into proper arguments
            # Use posix=False on Windows, posix=True on Unix-like systems
            command = shlex.split(manual_call_template.command_name, posix=(os.name != 'nt'))

            self._log_info(f"Executing command for tool discovery: {' '.join(command)}")

            stdout, stderr, return_code = await self._execute_command(
                command,
                env,
                timeout=30.0,
                working_dir=manual_call_template.working_dir,
            )

            # Get output based on exit code
            output = stdout if return_code == 0 else stderr

            if not output.strip():
                self._log_info(
                    f"No output from command '{manual_call_template.command_name}'"
                )
                return RegisterManualResult(
                    success=False,
                    manual_call_template=manual_call_template,
                    manual=UtcpManual(manual_version="0.0.0", tools=[]),
                    errors=[
                        f"No output from discovery command for CLI provider '{manual_call_template.name}'"
                    ],
                )

            # Try to parse UTCPManual from the output
            utcp_manual = self._extract_utcp_manual_from_output(
                output, manual_call_template.name
            )

            if utcp_manual is None:
                error_msg = (
                    f"Could not parse UTCP manual from CLI provider '{manual_call_template.name}' output"
                )
                self._log_error(error_msg)
                return RegisterManualResult(
                    success=False,
                    manual_call_template=manual_call_template,
                    manual=UtcpManual(manual_version="0.0.0", tools=[]),
                    errors=[error_msg],
                )

            self._log_info(
                f"Discovered {len(utcp_manual.tools)} tools from CLI provider '{manual_call_template.name}'"
            )
            return RegisterManualResult(
                success=True,
                manual_call_template=manual_call_template,
                manual=utcp_manual,
                errors=[],
            )

        except Exception as e:
            error_msg = f"Error discovering tools from CLI provider '{manual_call_template.name}': {e}"
            self._log_error(error_msg)
            return RegisterManualResult(
                success=False,
                manual_call_template=manual_call_template,
                manual=UtcpManual(manual_version="0.0.0", tools=[]),
                errors=[error_msg],
            )
    
    async def deregister_manual(self, caller, manual_call_template: CallTemplate) -> None:
        """REQUIRED
        Deregisters a CLI manual.

        For the CLI protocol, this is a no-op as there are no persistent
        connections to terminate.

        Args:
            caller: The UTCP client instance that is calling this method.
            manual_call_template: The call template of the manual to deregister.
        """
        if isinstance(manual_call_template, CliCallTemplate):
            self._log_info(
                f"Deregistering CLI manual '{manual_call_template.name}' (no-op)"
            )
    
    def _format_arguments(self, tool_args: Dict[str, Any]) -> List[str]:
        """Format arguments for command-line execution.
        
        Converts a dictionary of arguments into command-line flags and values.
        
        Args:
            tool_args: Dictionary of argument names and values
            
        Returns:
            List of command-line arguments
        """
        args = []
        for key, value in tool_args.items():
            if isinstance(value, bool):
                if value:
                    args.append(f"--{key}")
            elif isinstance(value, (list, tuple)):
                for item in value:
                    args.extend([f"--{key}", str(item)])
            else:
                args.extend([f"--{key}", str(value)])
        return args
    
    def _extract_utcp_manual_from_output(self, output: str, provider_name: str) -> Optional[UtcpManual]:
        """Extract a UTCP manual from command output.
        
        Tries to parse the output as a UTCP manual. If it instead looks like a list of tools,
        wraps them in a basic UtcpManual structure.
        """
        # Try to parse the entire output as JSON first
        try:
            data = json.loads(output.strip())
            if isinstance(data, dict) and "utcp_version" in data and "tools" in data:
                try:
                    return UtcpManualSerializer().validate_dict(data)
                except Exception as e:
                    self._log_error(
                        f"Invalid UTCP manual format from provider '{provider_name}': {e}"
                    )
                    # Fallback: try to parse tools from possibly-legacy structure
                    tools = self._parse_tool_data(data, provider_name)
                    if tools:
                        return UtcpManual(manual_version="0.0.0", tools=tools)
                    return None
            # Fallback: try to parse as tools
            tools = self._parse_tool_data(data, provider_name)
            if tools:
                return UtcpManual(manual_version="0.0.0", tools=tools)
        except json.JSONDecodeError:
            pass

        # Look for JSON objects within the output text and aggregate tools
        aggregated_tools: List[Tool] = []
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    data = json.loads(line)
                    # If a full manual is found in a line, return it immediately
                    if isinstance(data, dict) and "utcp_version" in data and "tools" in data:
                        try:
                            return UtcpManualSerializer().validate_dict(data)
                        except Exception as e:
                            self._log_error(
                                f"Invalid UTCP manual format from provider '{provider_name}': {e}"
                            )
                            # Fallback: try to parse tools from possibly-legacy structure
                            tools = self._parse_tool_data(data, provider_name)
                            if tools:
                                return UtcpManual(manual_version="0.0.0", tools=tools)
                            return None
                    found_tools = self._parse_tool_data(data, provider_name)
                    aggregated_tools.extend(found_tools)
                except json.JSONDecodeError:
                    continue

        if aggregated_tools:
            return UtcpManual(manual_version="0.0.0", tools=aggregated_tools)

        return None
    
    def _build_tool_from_dict(self, tool_data: Any, provider_name: str) -> Optional[Tool]:
        """Build a Tool object from a dictionary, supporting legacy keys.
        
        This maps legacy 'tool_provider' into the new 'tool_call_template'
        using the appropriate call template serializers.
        """
        try:
            if isinstance(tool_data, dict):
                # If already new-style and call template is a dict, validate it
                if "tool_call_template" in tool_data and isinstance(tool_data["tool_call_template"], dict):
                    td = dict(tool_data)
                    td["tool_call_template"] = CallTemplateSerializer().validate_dict(td["tool_call_template"])
                    return Tool(**td)
                
                # Legacy style: 'tool_provider'
                if "tool_provider" in tool_data and isinstance(tool_data["tool_provider"], dict):
                    provider = tool_data["tool_provider"]
                    provider_type = provider.get("provider_type") or provider.get("type")
                    # Normalize to call template dict
                    call_template_dict = {k: v for k, v in provider.items() if k != "provider_type"}
                    call_template_dict["type"] = provider_type
                    
                    # Validate based on type
                    if provider_type == "cli":
                        call_template = CliCallTemplateSerializer().validate_dict(call_template_dict)
                    else:
                        call_template = CallTemplateSerializer().validate_dict(call_template_dict)
                    
                    td = dict(tool_data)
                    td.pop("tool_provider", None)
                    td["tool_call_template"] = call_template
                    return Tool(**td)
                
                # Already a Tool-like dict with correct fields
                return Tool(**tool_data)
        except Exception as e:
            self._log_error(f"Invalid tool definition from provider '{provider_name}': {e}")
            return None
        return None
    
    def _parse_tool_data(self, data: Any, provider_name: str) -> List[Tool]:
        """Parse tool data from JSON.
        
        Supports both the new format (with 'tool_call_template') and the
        legacy format (with 'tool_provider').
        
        Args:
            data: JSON data to parse
            provider_name: Name of the provider for logging
            
        Returns:
            List of tools parsed from the data
        """
        tools: List[Tool] = []
        if isinstance(data, dict):
            if 'tools' in data and isinstance(data['tools'], list):
                for item in data['tools']:
                    built = self._build_tool_from_dict(item, provider_name)
                    if built is not None:
                        tools.append(built)
                return tools
            elif 'name' in data and 'description' in data:
                built = self._build_tool_from_dict(data, provider_name)
                return [built] if built is not None else []
        elif isinstance(data, list):
            for item in data:
                built = self._build_tool_from_dict(item, provider_name)
                if built is not None:
                    tools.append(built)
            return tools
        
        return tools
    
    async def call_tool(self, caller, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        """REQUIRED
        Calls a CLI tool by executing its command.

        This method constructs and executes the command specified in the
        `CliCallTemplate`. It formats the provided `tool_args` as command-line
        arguments and runs the command in a subprocess.

        Args:
            caller: The UTCP client instance that is calling this method.
            tool_name: The name of the tool to call.
            tool_args: A dictionary of arguments for the tool call.
            tool_call_template: The `CliCallTemplate` for the tool.

        Returns:
            The result of the command execution. If the command exits with a code
            of 0, it returns the content of stdout. If the exit code is non-zero,
            it returns the content of stderr. The output is parsed as JSON if
            possible; otherwise, it is returned as a raw string.

        Raises:
            ValueError: If `tool_call_template` is not an instance of
                `CliCallTemplate` or if `command_name` is not set.
        """
        if not isinstance(tool_call_template, CliCallTemplate):
            raise ValueError("CliCommunicationProtocol can only be used with CliCallTemplate")
        
        if not tool_call_template.command_name:
            raise ValueError(f"CliCallTemplate '{tool_call_template.name}' must have command_name set")
        
        # Build the command
        # Parse command string into proper arguments
        # Use posix=False on Windows, posix=True on Unix-like systems
        command = shlex.split(tool_call_template.command_name, posix=(os.name != 'nt'))
        
        # Add formatted arguments
        if tool_args:
            command.extend(self._format_arguments(tool_args))
        
        self._log_info(f"Executing CLI tool '{tool_name}': {' '.join(command)}")
        
        try:
            env = self._prepare_environment(tool_call_template)
            
            stdout, stderr, return_code = await self._execute_command(
                command,
                env,
                timeout=60.0,  # Longer timeout for tool execution
                working_dir=tool_call_template.working_dir
            )
            
            # Get output based on exit code
            if return_code == 0:
                output = stdout
                self._log_info(f"CLI tool '{tool_name}' executed successfully (exit code 0)")
            else:
                output = stderr
                self._log_info(f"CLI tool '{tool_name}' exited with code {return_code}, returning stderr")
            
            # Try to parse output as JSON, fall back to raw string
            if output.strip():
                try:
                    result = json.loads(output)
                    self._log_info(f"Returning JSON output from CLI tool '{tool_name}'")
                    return result
                except json.JSONDecodeError:
                    # Return raw string output
                    self._log_info(f"Returning text output from CLI tool '{tool_name}'")
                    return output.strip()
            else:
                self._log_info(f"CLI tool '{tool_name}' produced no output")
                return ""
            
        except Exception as e:
            self._log_error(f"Error executing CLI tool '{tool_name}': {e}")
            raise

    async def call_tool_streaming(self, caller, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any, None]:
        """REQUIRED
        Streaming calls are not supported for the CLI protocol.

        Raises:
            NotImplementedError: Always, as this functionality is not supported.
        """
        raise NotImplementedError("Streaming is not supported by the CLI communication protocol.")
