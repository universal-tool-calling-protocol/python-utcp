from typing import Literal
from pydantic import Field

from utcp.data.call_template import CallTemplate
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
        auth: Always None - text call templates don't support authentication.
    """

    call_template_type: Literal["text"] = "text"
    file_path: str = Field(..., description="The path to the file containing the UTCP manual or tool definitions.")
    auth: None = None


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
