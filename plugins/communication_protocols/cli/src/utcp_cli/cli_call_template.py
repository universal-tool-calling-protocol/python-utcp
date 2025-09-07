from typing import Optional, Dict, Literal
from pydantic import Field

from utcp.data.call_template import CallTemplate
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class CliCallTemplate(CallTemplate):
    """REQUIRED
    Call template configuration for Command Line Interface (CLI) tools.

    This class defines the configuration for executing command-line tools and
    programs as UTCP tool providers. It supports environment variable injection,
    custom working directories, and defines the command to be executed.

    Attributes:
        call_template_type: The type of the call template. Must be "cli".
        command_name: The command or path of the program to execute. It can
            contain placeholders for arguments that will be substituted at
            runtime (e.g., `${arg_name}`).
        env_vars: A dictionary of environment variables to set for the command's
            execution context. Values can be static strings or placeholders for
            variables from the UTCP client's variable substitutor.
        working_dir: The working directory from which to run the command. If not
            provided, it defaults to the current process's working directory.
        auth: Authentication details. Not applicable to the CLI protocol, so it
            is always None.

    Examples:
        Basic CLI command:
        ```json
        {
          "name": "list_files_tool",
          "call_template_type": "cli",
          "command_name": "ls -la",
          "working_dir": "/tmp"
        }
        ```

        Command with environment variables and argument placeholders:
        ```json
        {
          "name": "python_script_tool",
          "call_template_type": "cli",
          "command_name": "python script.py --input ${input_file}",
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
