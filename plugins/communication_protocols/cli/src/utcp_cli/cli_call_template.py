from typing import Optional, Dict, Literal
from pydantic import Field

from utcp.data.call_template import CallTemplate
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError


class CliCallTemplate(CallTemplate):
    """Call template configuration for Command Line Interface tools.

    Enables execution of command-line tools and programs as UTCP providers.
    Supports environment variable injection and custom working directories.

    Attributes:
        type: Always "cli" for CLI providers.
        command_name: The name or path of the command to execute.
        env_vars: Optional environment variables to set during command execution.
        working_dir: Optional custom working directory for command execution.
        auth: Always None - CLI providers don't support authentication.
    """

    type: Literal["cli"] = "cli"
    command_name: str
    env_vars: Optional[Dict[str, str]] = Field(
        default=None, description="Environment variables to set when executing the command"
    )
    working_dir: Optional[str] = Field(
        default=None, description="Working directory for command execution"
    )
    auth: None = None


class CliCallTemplateSerializer(Serializer[CliCallTemplate]):
    """Serializer for CliCallTemplate."""

    def to_dict(self, obj: CliCallTemplate) -> dict:
        return obj.model_dump()

    def validate_dict(self, obj: dict) -> CliCallTemplate:
        try:
            return CliCallTemplate.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid CliCallTemplate: " + str(e)) from e
