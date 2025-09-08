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
        description="Command string to execute, may contain UTCP_ARG_argname_UTCP_END placeholders"
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

    Attributes:
        call_template_type: The type of the call template. Must be "cli".
        commands: A list of CommandStep objects defining the commands to execute
            in order. Each command can contain UTCP_ARG_argname_UTCP_END placeholders
            that will be replaced with values from tool_args during execution.
        env_vars: A dictionary of environment variables to set for the command's
            execution context. Values can be static strings or placeholders for
            variables from the UTCP client's variable substitutor.
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

        Command with environment variables and placeholders:
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
          }
        }
        ```

    Security Considerations:
        - Commands are executed in a subprocess. Ensure that the commands
          specified are from a trusted source.
        - Avoid passing unsanitized user input directly into the command string.
          Use tool argument validation where possible.
        - All placeholders are replaced with string values from tool_args.
        - Commands should use the appropriate syntax for the target platform
          (PowerShell on Windows, Bash on Unix).
        - Previous command outputs are available as variables but should be
          used carefully to avoid command injection.
    """

    call_template_type: Literal["cli"] = "cli"
    commands: List[CommandStep] = Field(
        description="List of commands to execute in order. Each command can contain UTCP_ARG_argname_UTCP_END placeholders."
    )
    env_vars: Optional[Dict[str, str]] = Field(
        default=None, description="Environment variables to set when executing the commands"
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
