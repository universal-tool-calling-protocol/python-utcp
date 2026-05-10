from typing import Optional, Dict, Literal, List
from pydantic import Field, BaseModel

from utcp.data.call_template import CallTemplate
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class CommandStep(BaseModel):
    """REQUIRED
    Configuration for a single command step in a CLI execution flow.

    Attributes:
        command: The command string to execute. Can contain UTCP_ARG_argname_UTCP_END
            placeholders that will be replaced with values from tool_args. Can also
            reference previous command outputs using $CMD_0_OUTPUT, $CMD_1_OUTPUT, etc.

            Placeholder substitution is shell-quoted (`shlex.quote` on Unix,
            PowerShell single-quoted literals on Windows) so that
            `tool_args` values cannot inject extra commands. As a
            consequence, each `UTCP_ARG_..._UTCP_END` placeholder always
            expands to **exactly one shell token**. Tools that previously
            relied on a single placeholder splitting into multiple flags
            (e.g. `UTCP_ARG_flags_UTCP_END` -> `--verbose --debug`) must now
            use one placeholder per intended flag. This change ships with
            utcp-cli 1.1.2 and addresses GHSA-33p6-5jxp-p3x4.
        append_to_final_output: Whether this command's output should be included
            in the final result. If not specified, defaults to False for all
            commands except the last one.

    Examples:
        Basic command step:
        ```json
        {
          "command": "git status",
          "append_to_final_output": true
        }
        ```

        Command with argument placeholders and output reference:
        ```json
        {
          "command": "echo \"Cloning to: UTCP_ARG_target_dir_UTCP_END, previous status: $CMD_0_OUTPUT\"",
          "append_to_final_output": true
        }
        ```
    """
    command: str = Field(
        description=(
            "Command string to execute, may contain UTCP_ARG_argname_UTCP_END "
            "placeholders. Each placeholder is shell-quoted at substitution "
            "time and therefore expands to exactly one shell token; use one "
            "placeholder per intended argument."
        )
    )
    append_to_final_output: Optional[bool] = Field(
        default=None,
        description="Whether to include this command's output in final result. Defaults to False for all except last command"
    )

class CliCallTemplate(CallTemplate):
    """REQUIRED
    Call template configuration for Command Line Interface (CLI) tools.

    This class defines the configuration for executing command-line tools and
    programs as UTCP tool providers. Commands are executed in a single subprocess
    to maintain state (like directory changes) between commands.

    **Cross-Platform Script Generation:**
    - **Windows**: Commands are converted to a PowerShell script
    - **Unix/Linux/macOS**: Commands are converted to a Bash script

    **Command Syntax Requirements:**
    - Windows: Use PowerShell syntax (e.g., `Get-ChildItem`, `Set-Location`)
    - Unix: Use Bash/shell syntax (e.g., `ls`, `cd`)

    **Referencing Previous Command Output:**
    You can reference the output of previous commands using variables:
    - **PowerShell**: `$CMD_0_OUTPUT`, `$CMD_1_OUTPUT`, etc.
    - **Bash**: `$CMD_0_OUTPUT`, `$CMD_1_OUTPUT`, etc.

    Example: `echo "Previous result: $CMD_0_OUTPUT"`

    **Argument Substitution and Quoting (utcp-cli >= 1.1.2):**
    `UTCP_ARG_argname_UTCP_END` placeholders are replaced with the
    corresponding `tool_args` value, shell-quoted for the target shell
    (`shlex.quote` on Unix, PowerShell single-quoted literal on Windows).
    Each placeholder therefore expands to exactly one shell token. If a
    tool needs multiple flags or arguments, define multiple placeholders
    (one per flag) instead of relying on a single placeholder splitting
    on whitespace. This change closes the command-injection vector
    tracked as GHSA-33p6-5jxp-p3x4.

    **Subprocess Environment (utcp-cli >= 1.1.2):**
    The CLI subprocess no longer inherits the full host environment.
    Inheritance is controlled by `inherit_env_vars`:
      - Omitted / `null`: a built-in default allowlist of host variables
        is passed through (e.g. `PATH`, `PATHEXT`, `SYSTEMROOT`, `HOME`,
        `LANG`) so shells and binaries can be located normally.
      - `[]`: strict mode — nothing from the host environment is
        inherited; only `env_vars` is propagated.
      - `["FOO", "BAR"]`: exactly those host variables are passed
        through. The default allowlist is NOT merged in, so callers that
        still need `PATH` must list it explicitly.
    `env_vars` is always applied on top and overrides any inherited
    value. Values in `env_vars` may be plain strings or `${VARNAME}`
    style placeholders resolved by the UTCP client's variable
    substitutor (note: those placeholders are resolved against the UTCP
    client's variable sources, not against the host shell — to forward
    a host variable by name use `inherit_env_vars`). This closes the
    secret-exfiltration vector tracked as GHSA-5v57-8rxj-3p2r.

    Attributes:
        call_template_type: The type of the call template. Must be "cli".
        commands: A list of CommandStep objects defining the commands to execute
            in order. Each command can contain UTCP_ARG_argname_UTCP_END placeholders
            that will be replaced with values from tool_args during execution.
            Placeholders are shell-quoted and therefore expand to exactly one
            shell token (see class docstring).
        env_vars: A dictionary of environment variables to set for the command's
            execution context. Values can be static strings or placeholders for
            variables from the UTCP client's variable substitutor. Always
            propagated; overrides anything inherited from the host.
        inherit_env_vars: Controls which host environment variables are
            passed through to the subprocess.
              - `None` (default): the built-in default allowlist
                (`PATH`, `HOME`, `LANG` on Unix; `PATH`, `PATHEXT`,
                `SYSTEMROOT`, `USERPROFILE`, etc. on Windows) is
                inherited so shells and binaries work without extra
                configuration.
              - `[]`: strict mode — no host variables are inherited at
                all. Only `env_vars` reaches the subprocess.
              - `["FOO", "BAR"]`: exactly those host variables are
                inherited. The default allowlist is replaced, not
                extended, so include `PATH` (and any other required
                shell vars) yourself if needed.
            Variables named here that are not set on the host are
            silently skipped. Use this to expose specific host secrets
            such as `OPENAI_API_KEY`, `AWS_PROFILE`, `PYTHONPATH`, or
            `NODE_PATH` without putting their values in the call
            template.
        working_dir: The working directory from which to run the commands. If not
            provided, it defaults to the current process's working directory.
        auth: Authentication details. Not applicable to the CLI protocol, so it
            is always None.

    Examples:
        Cross-platform directory operations:
        ```json
        {
          "name": "cross_platform_dir_tool",
          "call_template_type": "cli",
          "commands": [
            {
              "command": "cd UTCP_ARG_target_dir_UTCP_END",
              "append_to_final_output": false
            },
            {
              "command": "ls -la",
              "append_to_final_output": true
            }
          ]
        }
        ```

        Referencing previous command output:
        ```json
        {
          "name": "reference_previous_output_tool",
          "call_template_type": "cli",
          "commands": [
            {
              "command": "git status --porcelain",
              "append_to_final_output": false
            },
            {
              "command": "echo \"Found changes: $CMD_0_OUTPUT\"",
              "append_to_final_output": true
            }
          ]
        }
        ```

        Command with environment variables, host pass-through, and placeholders:
        ```json
        {
          "name": "python_multi_step_tool",
          "call_template_type": "cli",
          "commands": [
            {
              "command": "python setup.py install",
              "append_to_final_output": false
            },
            {
              "command": "python script.py --input UTCP_ARG_input_file_UTCP_END --result \"$CMD_0_OUTPUT\""
            }
          ],
          "env_vars": {
            "PYTHONPATH": "/custom/path",
            "API_KEY": "${API_KEY_VAR}"
          },
          "inherit_env_vars": ["OPENAI_API_KEY", "AWS_PROFILE"]
        }
        ```

    Security Considerations:
        - Commands are executed in a subprocess. Ensure that the commands
          specified are from a trusted source.
        - `tool_args` values are shell-quoted on substitution, but the
          *command template itself* is not — never assemble it from
          untrusted input.
        - The host environment is restricted; secrets are not propagated
          unless explicitly named in `env_vars` or `inherit_env_vars`.
        - Commands should use the appropriate syntax for the target platform
          (PowerShell on Windows, Bash on Unix).
        - Previous command outputs are available as variables but should be
          used carefully to avoid command injection.
    """

    call_template_type: Literal["cli"] = "cli"
    commands: List[CommandStep] = Field(
        description=(
            "List of commands to execute in order. Each command can contain "
            "UTCP_ARG_argname_UTCP_END placeholders, which are shell-quoted "
            "on substitution and therefore expand to exactly one shell token."
        )
    )
    env_vars: Optional[Dict[str, str]] = Field(
        default=None,
        description=(
            "Environment variables to set when executing the commands. Always "
            "propagated to the subprocess and override values inherited from "
            "the host."
        )
    )
    inherit_env_vars: Optional[List[str]] = Field(
        default=None,
        description=(
            "Controls host environment inheritance. None (default) inherits "
            "a built-in safe allowlist (PATH, HOME / PATHEXT, SYSTEMROOT, "
            "etc.). [] disables host inheritance entirely. A list of names "
            "replaces the default allowlist with exactly those variables, so "
            "include PATH explicitly if your tool needs it. Names not set on "
            "the host are skipped silently."
        )
    )
    working_dir: Optional[str] = Field(
        default=None, description="Working directory for command execution"
    )
    auth: None = None


class CliCallTemplateSerializer(Serializer[CliCallTemplate]):
    """REQUIRED
    Serializer for converting between `CliCallTemplate` and dictionary representations.

    This class handles the serialization and deserialization of `CliCallTemplate`
    objects, ensuring that they can be correctly represented as dictionaries and
    reconstructed from them, with validation.
    """

    def to_dict(self, obj: CliCallTemplate) -> dict:
        """REQUIRED
        Converts a `CliCallTemplate` instance to its dictionary representation.

        Args:
            obj: The `CliCallTemplate` instance to serialize.

        Returns:
            A dictionary representing the `CliCallTemplate`.
        """
        return obj.model_dump()

    def validate_dict(self, obj: dict) -> CliCallTemplate:
        """REQUIRED
        Validates a dictionary and constructs a `CliCallTemplate` instance.

        Args:
            obj: The dictionary to validate and deserialize.

        Returns:
            A `CliCallTemplate` instance.

        Raises:
            UtcpSerializerValidationError: If the dictionary is not a valid
                representation of a `CliCallTemplate`.
        """
        try:
            return CliCallTemplate.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid CliCallTemplate: " + traceback.format_exc()) from e
