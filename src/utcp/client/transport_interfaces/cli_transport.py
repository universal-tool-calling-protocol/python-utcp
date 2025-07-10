"""
Command Line Interface (CLI) transport for UTCP client.

This transport executes command-line tools and processes.
"""
import asyncio
import json
import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Union

from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.shared.provider import Provider, CliProvider
from utcp.shared.tool import Tool
from utcp.shared.utcp_manual import UtcpManual


class CliTransport(ClientTransportInterface):
    """Transport implementation for CLI-based tool providers.
    
    This transport executes command-line tools and processes. It supports:
    - Tool discovery via startup commands that output tool definitions
    - Tool execution by running commands with arguments
    - Basic authentication via environment variables or command-line flags
    """
    
    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        """Initialize the CLI transport.
        
        Args:
            logger: Optional logger function for debugging
        """
        self._log = logger or (lambda *args, **kwargs: None)
    
    def _log_info(self, message: str):
        """Log informational messages."""
        self._log(f"[CliTransport] {message}")
        
    def _log_error(self, message: str):
        """Log error messages."""
        logging.error(f"[CliTransport Error] {message}")
    
    def _prepare_environment(self, provider: CliProvider) -> Dict[str, str]:
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
    
    async def register_tool_provider(self, manual_provider: Provider) -> List[Tool]:
        """Register a CLI provider and discover its tools.
        
        Executes the provider's command_name and looks for UTCPManual JSON in the output.
        
        Args:
            manual_provider: The CliProvider to register
            
        Returns:
            List of tools discovered from the CLI provider
            
        Raises:
            ValueError: If provider is not a CliProvider or command_name is not set
        """
        if not isinstance(manual_provider, CliProvider):
            raise ValueError("CliTransport can only be used with CliProvider")
        
        if not manual_provider.command_name:
            raise ValueError(f"CliProvider '{manual_provider.name}' must have command_name set")
        
        self._log_info(f"Registering CLI provider '{manual_provider.name}' with command '{manual_provider.command_name}'")
        
        try:
            env = self._prepare_environment(manual_provider)
            # Parse command string into proper arguments
            # Use posix=False on Windows, posix=True on Unix-like systems
            command = shlex.split(manual_provider.command_name, posix=(os.name != 'nt'))
            
            self._log_info(f"Executing command for tool discovery: {' '.join(command)}")
            
            stdout, stderr, return_code = await self._execute_command(
                command,
                env,
                timeout=30.0,
                working_dir=manual_provider.working_dir
            )
            
            # Get output based on exit code
            output = stdout if return_code == 0 else stderr
            
            if not output.strip():
                self._log_info(f"No output from command '{manual_provider.command_name}'")
                return []
            
            # Try to find UTCPManual JSON within the output
            tools = self._extract_utcp_manual_from_output(output, manual_provider.name)
            
            self._log_info(f"Discovered {len(tools)} tools from CLI provider '{manual_provider.name}'")
            return tools
            
        except Exception as e:
            self._log_error(f"Error discovering tools from CLI provider '{manual_provider.name}': {e}")
            return []
    
    async def deregister_tool_provider(self, manual_provider: Provider) -> None:
        """Deregister a CLI provider.
        
        This is a no-op for CLI providers since they are stateless.
        
        Args:
            manual_provider: The provider to deregister
        """
        if isinstance(manual_provider, CliProvider):
            self._log_info(f"Deregistering CLI provider '{manual_provider.name}' (no-op)")
    
    def _format_arguments(self, arguments: Dict[str, Any]) -> List[str]:
        """Format arguments for command-line execution.
        
        Converts a dictionary of arguments into command-line flags and values.
        
        Args:
            arguments: Dictionary of argument names and values
            
        Returns:
            List of command-line arguments
        """
        args = []
        for key, value in arguments.items():
            if isinstance(value, bool):
                if value:
                    args.append(f"--{key}")
            elif isinstance(value, (list, tuple)):
                for item in value:
                    args.extend([f"--{key}", str(item)])
            else:
                args.extend([f"--{key}", str(value)])
        return args
    
    def _extract_utcp_manual_from_output(self, output: str, provider_name: str) -> List[Tool]:
        """Extract UTCPManual JSON from command output.
        
        Searches for JSON content that matches UTCPManual format within the output text.
        
        Args:
            output: The command output to search
            provider_name: Name of the provider for logging
            
        Returns:
            List of tools found in the output
        """
        tools = []
        
        # Try to parse the entire output as JSON first
        try:
            data = json.loads(output.strip())
            tools = self._parse_tool_data(data, provider_name)
            if tools:
                return tools
        except json.JSONDecodeError:
            pass
        
        # Look for JSON objects within the output text
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    data = json.loads(line)
                    found_tools = self._parse_tool_data(data, provider_name)
                    tools.extend(found_tools)
                except json.JSONDecodeError:
                    continue
        
        return tools
    
    def _parse_tool_data(self, data: Any, provider_name: str) -> List[Tool]:
        """Parse tool data from JSON.
        
        Args:
            data: JSON data to parse
            provider_name: Name of the provider for logging
            
        Returns:
            List of tools parsed from the data
        """
        if isinstance(data, dict):
            if 'tools' in data:
                # Standard UTCP manual format
                try:
                    utcp_manual = UtcpManual(**data)
                    return utcp_manual.tools
                except Exception as e:
                    self._log_error(f"Invalid UTCP manual format from provider '{provider_name}': {e}")
                    return []
            elif 'name' in data and 'description' in data:
                # Single tool definition
                try:
                    return [Tool(**data)]
                except Exception as e:
                    self._log_error(f"Invalid tool definition from provider '{provider_name}': {e}")
                    return []
        elif isinstance(data, list):
            # Array of tool definitions
            try:
                return [Tool(**tool_data) for tool_data in data]
            except Exception as e:
                self._log_error(f"Invalid tool array from provider '{provider_name}': {e}")
                return []
        
        return []
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], tool_provider: Provider) -> Any:
        """Call a CLI tool.
        
        Executes the command specified by provider.command_name with the provided arguments.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments for the tool call
            tool_provider: The CliProvider containing the tool
            
        Returns:
            The output from the command execution based on exit code:
            - If exit code is 0: stdout (parsed as JSON if possible, otherwise raw string)
            - If exit code is not 0: stderr
            
        Raises:
            ValueError: If provider is not a CliProvider or command_name is not set
        """
        if not isinstance(tool_provider, CliProvider):
            raise ValueError("CliTransport can only be used with CliProvider")
        
        if not tool_provider.command_name:
            raise ValueError(f"CliProvider '{tool_provider.name}' must have command_name set")
        
        # Build the command
        # Parse command string into proper arguments
        # Use posix=False on Windows, posix=True on Unix-like systems
        command = shlex.split(tool_provider.command_name, posix=(os.name != 'nt'))
        
        # Add formatted arguments
        if arguments:
            command.extend(self._format_arguments(arguments))
        
        self._log_info(f"Executing CLI tool '{tool_name}': {' '.join(command)}")
        
        try:
            env = self._prepare_environment(tool_provider)
            
            stdout, stderr, return_code = await self._execute_command(
                command,
                env,
                timeout=60.0,  # Longer timeout for tool execution
                working_dir=tool_provider.working_dir
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
    
    async def close(self) -> None:
        """Close the transport.
        
        This is a no-op for CLI transports since they don't maintain connections.
        """
        self._log_info("Closing CLI transport (no-op)")
