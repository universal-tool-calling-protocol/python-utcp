from typing import Optional, Dict, Literal
from pydantic import Field

from utcp.data.call_template import CallTemplate
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class CliCallTemplate(CallTemplate):
    """REQUIRED
    Call template configuration for Command Line Interface tools.

    Enables execution of command-line tools and programs as UTCP providers.
    Supports environment variable injection and custom working directories.

    Configuration Examples:
        Basic CLI command:
        ```json
        {
          "name": "file_tools",
          "call_template_type": "cli",
          "command_name": "ls -la ${path}",
          "working_dir": "/tmp"
        }
        ```

        With environment variables:
        ```json
        {
          "name": "env_tool",
          "call_template_type": "cli",
          "command_name": "python script.py ${input}",
          "env_vars": {
            "PYTHONPATH": "/custom/path",
            "API_KEY": "${API_KEY}"
          }
        }
        ```

        Processing stdin:
        ```json
        {
          "name": "processor",
          "call_template_type": "cli",
          "command_name": "jq .data",
          "stdin": "${json_input}",
          "timeout": 10
        }
        ```

        Safe command with argument validation:
        ```json
        {
          "name": "safe_tool",
          "call_template_type": "cli",
          "command_name": "grep ${pattern} ${file}",
          "working_dir": "/safe/directory",
          "allowed_args": {
            "pattern": "^[a-zA-Z0-9_-]+$",
            "file": "^[a-zA-Z0-9_./-]+\\.txt$"
          }
        }
        ```

    Security Considerations:
        - Commands are executed in a subprocess with the same OS privileges as the running process
        - Environment variables can be used to pass sensitive data securely
        - Working directory can be restricted to safe locations
        - Input validation should be implemented for user-provided arguments

    Attributes:
        call_template_type: Always "cli" for CLI providers.
        command_name: The name or path of the command to execute.
        env_vars: Optional environment variables to set during command execution.
        working_dir: Optional custom working directory for command execution.
        auth: Always None - CLI providers don't support authentication.
    """

    call_template_type: Literal["cli"] = "cli"
    command_name: str
    env_vars: Optional[Dict[str, str]] = Field(
        default=None, description="Environment variables to set when executing the command"
    )
    working_dir: Optional[str] = Field(
        default=None, description="Working directory for command execution"
    )
    auth: None = None


class CliCallTemplateSerializer(Serializer[CliCallTemplate]):
    """REQUIRED
    Serializer for CliCallTemplate."""

    def to_dict(self, obj: CliCallTemplate) -> dict:
        """REQUIRED
        Converts a CliCallTemplate to a dictionary."""
        return obj.model_dump()

    def validate_dict(self, obj: dict) -> CliCallTemplate:
        """REQUIRED
        Validates a dictionary and returns a CliCallTemplate."""
        try:
            return CliCallTemplate.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid CliCallTemplate: " + traceback.format_exc()) from e
