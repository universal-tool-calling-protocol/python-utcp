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
    - Cross-platform command parsing for Windows and Unix-like systems.

Security Considerations:
    Executing arbitrary command-line tools can be dangerous. This protocol
    should only be used with trusted tools.
"""
import asyncio
import json
import os
import re
import secrets
import sys
from typing import Dict, Any, List, Optional, Tuple, AsyncGenerator

from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplate, CallTemplateSerializer
from utcp.data.tool import Tool
from utcp.data.utcp_manual import UtcpManual, UtcpManualSerializer
from utcp.data.register_manual_response import RegisterManualResult
from utcp_cli.cli_call_template import CliCallTemplate, CliCallTemplateSerializer, CommandStep
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
    
    # Default set of host environment variables propagated to the CLI
    # subprocess when `CliCallTemplate.inherit_env_vars` is not provided
    # (i.e. None). Locating binaries (`PATH` / `PATHEXT`), basic shell +
    # locale state, and Windows runtime paths are needed for almost any
    # tool to start. Anything else (cloud creds, API keys, internal
    # tokens) must be opted in by listing the variable name explicitly in
    # `inherit_env_vars`, or its value provided in `env_vars`.
    #
    # If `inherit_env_vars == []`, the caller is opting into strict mode
    # and NOTHING is inherited from the host — only `env_vars` reaches the
    # subprocess.
    #
    # Backs GHSA-5v57-8rxj-3p2r: the previous implementation handed
    # `os.environ.copy()` to the subprocess, which combined with the
    # command injection in `_substitute_utcp_args`
    # (GHSA-33p6-5jxp-p3x4) let an attacker exfiltrate every secret in
    # the host process.
    _DEFAULT_INHERITED_KEYS_UNIX: tuple = (
        "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "USER", "LOGNAME",
        "SHELL", "TZ", "TERM",
    )
    _DEFAULT_INHERITED_KEYS_WINDOWS: tuple = (
        "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
        "TEMP", "TMP", "USERPROFILE", "USERNAME", "USERDOMAIN", "COMPUTERNAME",
        "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
        "ALLUSERSPROFILE", "PUBLIC",
        "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "OS",
        "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER",
        "PROCESSOR_LEVEL", "PROCESSOR_REVISION", "NUMBER_OF_PROCESSORS",
        # PowerShell + login session bits. Without PSMODULEPATH in
        # particular, powershell.exe has to enumerate module roots from
        # scratch on first use, which can cost 5-15s on CI runners and
        # silently push the discovery flow past its timeout.
        "PSMODULEPATH", "LOGONSERVER", "SESSIONNAME", "USERDNSDOMAIN",
    )

    @classmethod
    def _default_inherited_keys(cls) -> tuple:
        """Return the platform-appropriate default inheritance list."""
        if os.name == 'nt':
            return cls._DEFAULT_INHERITED_KEYS_WINDOWS
        return cls._DEFAULT_INHERITED_KEYS_UNIX

    def _prepare_environment(self, provider: CliCallTemplate) -> Dict[str, str]:
        """Prepare environment variables for command execution.

        Composes the subprocess environment with one layer of host
        inheritance (controlled by `provider.inherit_env_vars`) plus
        `provider.env_vars` on top:

          - `inherit_env_vars is None` (default): pass through the
            built-in default allowlist of host vars (PATH, HOME / PATHEXT,
            SYSTEMROOT, etc.) so normal shells and binaries work without
            extra wiring.
          - `inherit_env_vars == []`: strict mode. Nothing from the host
            environment reaches the subprocess — only `env_vars`.
          - `inherit_env_vars == [...]`: pass through exactly the named
            host variables. The default allowlist is NOT merged in, so
            callers who still want PATH must include it explicitly.

        `env_vars` is always applied last and overrides anything inherited
        from the host.

        This prevents the unrestricted host environment from leaking into
        a subprocess that may be running attacker-controlled commands
        (GHSA-5v57-8rxj-3p2r).

        Args:
            provider: The CLI provider

        Returns:
            Environment variables dictionary
        """
        if provider.inherit_env_vars is None:
            inherited_keys: tuple = self._default_inherited_keys()
        else:
            inherited_keys = tuple(provider.inherit_env_vars)

        env: Dict[str, str] = {}
        for key in inherited_keys:
            value = os.environ.get(key)
            if value is not None:
                env[key] = value

        # Caller-supplied variables override anything inherited from the
        # host. Unset host vars in `inherited_keys` are skipped silently
        # so missing optionals don't break tool execution.
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

        if not manual_call_template.commands:
            raise ValueError(f"CliCallTemplate '{manual_call_template.name}' must have at least one command")

        self._log_info(
            f"Registering CLI manual '{manual_call_template.name}' with {len(manual_call_template.commands)} command(s)"
        )

        try:
            # Execute commands using the same approach as call_tool but with no arguments
            base_env = self._prepare_environment(manual_call_template)
            shell_script, arg_env = self._build_combined_shell_script(
                manual_call_template.commands, {}
            )
            # Per-call __UTCP_ARG_* env vars carry placeholder values;
            # layer them on top of the inherited+caller-supplied env so
            # the references emitted into the script actually resolve.
            env = {**base_env, **arg_env}

            self._log_info(f"Executing shell script for tool discovery from provider '{manual_call_template.name}'")

            stdout, stderr, return_code = await self._execute_shell_script(
                shell_script,
                env,
                # 60s, not 30s: Windows PowerShell startup on CI
                # runners can be slow (especially the first time
                # in a session, before module path caches warm up).
                # Discovery runs once per manual, so a generous
                # ceiling here is cheap.
                timeout=60.0,
                working_dir=manual_call_template.working_dir,
            )

            # Get output based on exit code
            output = stdout if return_code == 0 else stderr

            if not output.strip():
                self._log_info(
                    f"No output from commands for CLI provider '{manual_call_template.name}'"
                )
                return RegisterManualResult(
                    success=False,
                    manual_call_template=manual_call_template,
                    manual=UtcpManual(manual_version="0.0.0", tools=[]),
                    errors=[
                        f"No output from discovery commands for CLI provider '{manual_call_template.name}'"
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
    
    @staticmethod
    def _make_nonce() -> str:
        """Generate an unguessable nonce that namespaces the env vars used
        for argument substitution within a single tool invocation.

        Prevents a template author from being able to write a literal
        ``${__UTCP_ARG_<nonce>_<name>}`` reference that collides with our
        substitution slot, which would re-introduce
        unquoted-variable-expansion injection.
        """
        return secrets.token_hex(8)

    @staticmethod
    def _env_var_name(nonce: str, arg_name: str) -> str:
        """Compute the env-var name that carries one substituted tool_arg
        value into the subprocess. The nonce is fresh per invocation so
        ``${__UTCP_ARG_<nonce>_<name>}`` literals cannot exist in
        templates authored before invocation time.
        """
        return f"__UTCP_ARG_{nonce}_{arg_name}"

    _PLACEHOLDER_RE = re.compile(r'UTCP_ARG_([a-zA-Z0-9_]+?)_UTCP_END')

    def _substitute_utcp_args(
        self,
        command: str,
        tool_args: Dict[str, Any],
        nonce: str,
    ) -> Tuple[str, Dict[str, str]]:
        """Substitute ``UTCP_ARG_<name>_UTCP_END`` placeholders in a
        command string by emitting context-appropriate shell variable
        references and recording the actual values as env vars on the
        returned dict. The caller wires those env vars into the
        subprocess (alongside the call template's ``env_vars`` and the
        host-inheritance allowlist) so the shell expands them at
        runtime, AFTER it has already parsed the script. As a result,
        attacker-controlled ``tool_args`` never get spliced into the
        script source and therefore cannot inject commands or escape
        any quoting context.

        Quote-state tracking ensures the emitted reference is correct
        for its surrounding context:

          bash (Unix):
            - bare:                ``"$VAR"``      (quoted: no word splitting)
            - inside double quotes: ``${VAR}``     (bash expands inside dq)
            - inside single quotes: ``'"$VAR"'``   (close sq, dq with var,
                                                   reopen sq -- bash treats
                                                   adjacent quoted regions
                                                   as a single token)

          powershell (Windows):
            - bare:                ``${env:VAR}``
            - inside double quotes: ``${env:VAR}``  (PS expands inside dq;
                                                     braced form prevents
                                                     suffix characters
                                                     from being consumed
                                                     into the var name)
            - inside single quotes: ValueError -- PS does not expand inside
                                                  single-quoted strings, so
                                                  we cannot safely
                                                  substitute without
                                                  rewriting the entire
                                                  surrounding token. Author
                                                  must use a double-quoted
                                                  string.

        Backs GHSA-33p6-5jxp-p3x4. An earlier fix that did inline
        ``shlex.quote``-style substitution was still vulnerable when
        the placeholder sat inside a surrounding ``"`` region: e.g.
        template ``curl "https://api/UTCP_ARG_id_UTCP_END"`` with
        ``id = '"; rm -rf /; "'`` produced
        ``curl "https://api/'"; rm -rf /; "'"``, where bash's parser
        closed the outer dq early and ran the injected commands.

        Args:
            command: Command string containing
                ``UTCP_ARG_<name>_UTCP_END`` placeholders.
            tool_args: Dictionary of argument names and values.
            nonce: Per-invocation nonce used to namespace generated env
                vars.

        Returns:
            Tuple ``(command, env)`` where ``command`` is safe to embed
            in a shell script and ``env`` is the additional env vars
            the subprocess must receive for the references to expand.
        """
        if os.name == 'nt':
            return self._substitute_powershell(command, tool_args, nonce)
        return self._substitute_bash(command, tool_args, nonce)

    def _substitute_bash(
        self,
        command: str,
        tool_args: Dict[str, Any],
        nonce: str,
    ) -> Tuple[str, Dict[str, str]]:
        env: Dict[str, str] = {}
        out: List[str] = []
        state = "normal"  # "normal" | "dq" | "sq"
        i = 0
        n = len(command)

        def collect(name: str) -> str:
            v = self._env_var_name(nonce, name)
            if name in tool_args:
                env[v] = str(tool_args[name])
            else:
                self._log_error(
                    f"Missing argument '{name}' for placeholder in command: {command}"
                )
                env[v] = f"MISSING_ARG_{name}"
            return v

        while i < n:
            m = self._PLACEHOLDER_RE.match(command, i)
            if m is not None:
                v = collect(m.group(1))
                if state == "normal":
                    out.append(f'"${v}"')
                elif state == "dq":
                    out.append(f"${{{v}}}")
                else:  # sq -- break out, dq the var, reopen sq
                    out.append(f"'\"${v}\"'")
                i = m.end()
                continue

            ch = command[i]
            if state == "normal":
                if ch == "'":
                    state = "sq"
                    out.append(ch)
                elif ch == '"':
                    state = "dq"
                    out.append(ch)
                elif ch == "\\" and i + 1 < n:
                    out.append(ch)
                    out.append(command[i + 1])
                    i += 2
                    continue
                else:
                    out.append(ch)
            elif state == "dq":
                if ch == "\\" and i + 1 < n and command[i + 1] in '"\\$`\n':
                    out.append(ch)
                    out.append(command[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    state = "normal"
                    out.append(ch)
                else:
                    out.append(ch)
            else:  # sq -- only `'` ends the string. No expansion, no escapes.
                if ch == "'":
                    state = "normal"
                    out.append(ch)
                else:
                    out.append(ch)
            i += 1

        return "".join(out), env

    def _substitute_powershell(
        self,
        command: str,
        tool_args: Dict[str, Any],
        nonce: str,
    ) -> Tuple[str, Dict[str, str]]:
        env: Dict[str, str] = {}
        out: List[str] = []
        state = "normal"  # "normal" | "dq" | "sq"
        i = 0
        n = len(command)

        def collect(name: str) -> str:
            v = self._env_var_name(nonce, name)
            if name in tool_args:
                env[v] = str(tool_args[name])
            else:
                self._log_error(
                    f"Missing argument '{name}' for placeholder in command: {command}"
                )
                env[v] = f"MISSING_ARG_{name}"
            return v

        while i < n:
            m = self._PLACEHOLDER_RE.match(command, i)
            if m is not None:
                if state == "sq":
                    raise ValueError(
                        f"Placeholder UTCP_ARG_{m.group(1)}_UTCP_END appears "
                        f"inside a PowerShell single-quoted string in "
                        f"command: {command}\n"
                        f"PowerShell does not expand variables inside single "
                        f"quotes, so this cannot be substituted safely. Use a "
                        f'double-quoted string ("...") around the placeholder '
                        f"instead."
                    )
                v = collect(m.group(1))
                # Use the braced form `${env:VAR}` rather than `$env:VAR`
                # so the variable name is explicitly delimited. The bare
                # form lets PowerShell's lexer keep consuming
                # alphanumerics + `_` until it hits a non-identifier
                # char, which would silently swallow any suffix text in
                # the template (e.g. template
                # ``"URL=UTCP_ARG_id_UTCP_END123"`` would be substituted
                # as ``"URL=$env:__UTCP_ARG_<nonce>_id123"`` and resolve
                # an env var that does not exist). Braces close that
                # boundary cleanly.
                out.append("${env:" + v + "}")
                i = m.end()
                continue

            ch = command[i]
            if state == "normal":
                if ch == "'":
                    state = "sq"
                    out.append(ch)
                elif ch == '"':
                    state = "dq"
                    out.append(ch)
                elif ch == "`" and i + 1 < n:
                    out.append(ch)
                    out.append(command[i + 1])
                    i += 2
                    continue
                else:
                    out.append(ch)
            elif state == "dq":
                if ch == "`" and i + 1 < n:
                    out.append(ch)
                    out.append(command[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    state = "normal"
                    out.append(ch)
                else:
                    out.append(ch)
            else:  # sq -- PS: `''` is an escaped single quote inside the literal.
                if ch == "'" and i + 1 < n and command[i + 1] == "'":
                    out.append(ch)
                    out.append(command[i + 1])
                    i += 2
                    continue
                if ch == "'":
                    state = "normal"
                    out.append(ch)
                else:
                    out.append(ch)
            i += 1

        return "".join(out), env
    
    def _build_combined_shell_script(
        self,
        commands: List[CommandStep],
        tool_args: Dict[str, Any],
    ) -> Tuple[str, Dict[str, str]]:
        """Build a combined shell script from multiple commands.

        Returns both the script and the env-var contributions
        accumulated across all command steps. Callers must merge these
        env vars into the subprocess environment so the placeholder
        references the script writes (``$VAR`` / ``${VAR}`` /
        ``$env:VAR``) actually resolve to the original tool_arg values
        at runtime.

        Args:
            commands: List of CommandStep objects to combine
            tool_args: Tool arguments for placeholder substitution

        Returns:
            Tuple ``(script, env)`` -- script is the shell script
            source, env is the additional ``__UTCP_ARG_*`` env vars to
            inject.
        """
        script_lines: List[str] = []
        accumulated_env: Dict[str, str] = {}
        # One nonce per script -- shared across all command steps so the
        # env-var contributions land in a consistent namespace.
        nonce = self._make_nonce()

        # Add error handling and setup
        if os.name == 'nt':
            # PowerShell script
            script_lines.append('$ErrorActionPreference = "Stop"')  # Exit on error
            script_lines.append('# Variables to store command outputs')
        else:
            # Unix shell script
            script_lines.append('#!/bin/bash')
            # Don't use set -e to allow error output capture and processing
            script_lines.append('# Variables to store command outputs')

        # Execute each command and store output in variables
        for i, command_step in enumerate(commands):
            # Substitute UTCP_ARG placeholders -- emits shell-variable
            # references, contributes the actual values via env.
            substituted_command, step_env = self._substitute_utcp_args(
                command_step.command, tool_args, nonce
            )
            accumulated_env.update(step_env)

            var_name = f"CMD_{i}_OUTPUT"

            if os.name == 'nt':
                # PowerShell - capture command output in variable
                script_lines.append(f'${var_name} = {substituted_command} 2>&1 | Out-String')
            else:
                # Unix shell - capture command output in variable
                script_lines.append(f'{var_name}=$({substituted_command} 2>&1)')
        
        # Echo only the outputs we want based on append_to_final_output
        for i, command_step in enumerate(commands):
            is_last_command = i == len(commands) - 1
            should_append = command_step.append_to_final_output
            
            if should_append is None:
                # Default: only append the last command's output
                should_append = is_last_command
            
            if should_append:
                var_name = f"CMD_{i}_OUTPUT"
                if os.name == 'nt':
                    # PowerShell
                    script_lines.append(f'Write-Output ${var_name}')
                else:
                    # Unix shell
                    script_lines.append(f'echo "${{{var_name}}}"')

        return '\n'.join(script_lines), accumulated_env
    
    async def _execute_shell_script(self, script: str, env: Dict[str, str], timeout: float = 60.0, working_dir: Optional[str] = None) -> tuple[str, str, int]:
        """Execute a shell script in a single subprocess.
        
        Args:
            script: Shell script content to execute
            env: Environment variables
            timeout: Timeout in seconds
            working_dir: Working directory for script execution
            
        Returns:
            Tuple of (stdout, stderr, return_code)
        """
        process = None
        try:
            # Choose shell based on OS
            if os.name == 'nt':
                # Windows: use PowerShell
                shell_cmd = ['powershell.exe', '-Command']
            else:
                # Unix: use bash
                shell_cmd = ['/bin/bash', '-c']
            
            # Add the script as the last argument
            full_command = shell_cmd + [script]
            
            process = await asyncio.create_subprocess_exec(
                *full_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=working_dir
            )
            
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            stdout = stdout_bytes.decode('utf-8', errors='replace')
            stderr = stderr_bytes.decode('utf-8', errors='replace')
            
            return stdout, stderr, process.returncode or 0
            
        except asyncio.TimeoutError:
            if process:
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
            self._log_error(f"Shell script timed out after {timeout} seconds")
            raise
        except Exception as e:
            if process:
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
            self._log_error(f"Error executing shell script: {e}")
            raise
    
    def _parse_combined_output(self, stdout: str, stderr: str, return_code: int, commands: List[CommandStep], tool_name: str) -> Any:
        """Parse output from combined shell script execution.
        
        Args:
            stdout: Standard output from shell script
            stderr: Standard error from shell script
            return_code: Exit code of shell script
            commands: Original commands list for output control (unused with variable approach)
            tool_name: Name of the tool for logging
            
        Returns:
            Final output from script (already filtered by append_to_final_output)
        """
        # Platform-specific output handling
        if os.name == 'nt':
            # Windows (PowerShell): Use stdout on success, stderr on failure
            output = stdout if return_code == 0 else stderr
        else:
            # Unix (Bash): Our script captures everything and echoes to stdout
            # So we always use stdout first, fallback to stderr if stdout is empty
            output = stdout if stdout.strip() else stderr
        
        if not output.strip():
            self._log_info(f"CLI tool '{tool_name}' produced no output")
            return ""
        
        # With the variable approach, output is already filtered - just return it
        output = output.strip()
        
        # Try to parse as JSON if it looks like JSON
        if output.startswith(('{', '[')):
            try:
                result = json.loads(output)
                self._log_info(f"Returning JSON output from CLI tool '{tool_name}'")
                return result
            except json.JSONDecodeError:
                pass
        
        self._log_info(f"Returning text output from CLI tool '{tool_name}'")
        return output
    
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
            it returns the content of stderr.

        Raises:
            ValueError: If `tool_call_template` is not an instance of
                `CliCallTemplate` or if `command_name` is not set.
        """
        if not isinstance(tool_call_template, CliCallTemplate):
            raise ValueError("CliCommunicationProtocol can only be used with CliCallTemplate")
        
        if not tool_call_template.commands:
            raise ValueError(f"CliCallTemplate '{tool_call_template.name}' must have at least one command")
        
        self._log_info(f"Executing CLI tool '{tool_name}' with {len(tool_call_template.commands)} command(s) in single subprocess")
        
        try:
            base_env = self._prepare_environment(tool_call_template)

            # Build combined shell script with output capture. The
            # script's placeholders are emitted as `$VAR` / `${VAR}` /
            # `$env:VAR` references; the actual tool_arg values come
            # back as `arg_env`.
            shell_script, arg_env = self._build_combined_shell_script(
                tool_call_template.commands, tool_args
            )
            env = {**base_env, **arg_env}

            self._log_info("Executing combined shell script")
            
            # Execute the combined script in a single subprocess
            stdout, stderr, return_code = await self._execute_shell_script(
                shell_script,
                env,
                timeout=120.0,  # Longer timeout for multi-command execution
                working_dir=tool_call_template.working_dir
            )
            
            # Parse the output to extract individual command outputs
            final_output = self._parse_combined_output(stdout, stderr, return_code, tool_call_template.commands, tool_name)
            
            return final_output
            
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
