from typing import Literal, Optional, Any
from pydantic import Field, field_serializer, field_validator

from utcp.data.call_template import CallTemplate
from utcp.data.auth import Auth, AuthSerializer
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class TextCallTemplate(CallTemplate):
    """REQUIRED
    Call template for text file-based manuals and tools.

    Reads UTCP manuals or tool definitions from local JSON/YAML files. Useful for
    static tool configurations or environments where manuals are distributed as files.

    Attributes:
        call_template_type: Always "text" for text file call templates.
        file_path: Path to the file containing the UTCP manual or tool definitions.
        auth: Always None - text call templates don't support authentication for file access.
        auth_tools: Optional authentication to apply to generated tools from OpenAPI specs.
    """

    call_template_type: Literal["text"] = "text"
    file_path: str = Field(..., description="The path to the file containing the UTCP manual or tool definitions.")
    auth: None = None
    auth_tools: Optional[Auth] = Field(None, description="Authentication to apply to generated tools from OpenAPI specs.")

    @field_serializer('auth_tools')
    def serialize_auth_tools(self, auth_tools: Optional[Auth]) -> Optional[dict]:
        """Serialize auth_tools to dictionary."""
        if auth_tools is None:
            return None
        return AuthSerializer().to_dict(auth_tools)

    @field_validator('auth_tools', mode='before')
    @classmethod
    def validate_auth_tools(cls, v: Any) -> Optional[Auth]:
        """Validate and deserialize auth_tools from dictionary."""
        if v is None:
            return None
        if isinstance(v, Auth):
            return v
        if isinstance(v, dict):
            return AuthSerializer().validate_dict(v)
        raise ValueError(f"auth_tools must be None, Auth instance, or dict, got {type(v)}")


class TextCallTemplateSerializer(Serializer[TextCallTemplate]):
    """REQUIRED
    Serializer for TextCallTemplate."""

    def to_dict(self, obj: TextCallTemplate) -> dict:
        """REQUIRED
        Convert a TextCallTemplate to a dictionary."""
        return obj.model_dump()

    def validate_dict(self, obj: dict) -> TextCallTemplate:
        """REQUIRED
        Validate and convert a dictionary to a TextCallTemplate."""
        try:
            return TextCallTemplate.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid TextCallTemplate: " + traceback.format_exc())
