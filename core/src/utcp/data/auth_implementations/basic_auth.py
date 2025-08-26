from utcp.data.auth import Auth
from utcp.interfaces.serializer import Serializer
from pydantic import Field, ValidationError
from typing import Literal
from utcp.exceptions import UtcpSerializerValidationError

class BasicAuth(Auth):
    """REQUIRED
    Authentication using HTTP Basic Authentication.

    Uses the standard HTTP Basic Authentication scheme with username and password
    encoded in the Authorization header.

    Attributes:
        auth_type: The authentication type identifier, always "basic".
        username: The username for basic authentication. Recommended to use injected variables.
        password: The password for basic authentication. Recommended to use injected variables.
    """

    auth_type: Literal["basic"] = "basic"
    username: str = Field(..., description="The username for basic authentication.")
    password: str = Field(..., description="The password for basic authentication.")


class BasicAuthSerializer(Serializer[BasicAuth]):
    """REQUIRED
    Serializer for BasicAuth model."""
    def to_dict(self, obj: BasicAuth) -> dict:
        """REQUIRED
        Convert a BasicAuth object to a dictionary.

        Args:
            obj: The BasicAuth object to convert.

        Returns:
            The dictionary converted from the BasicAuth object.
        """
        return obj.model_dump()
    
    def validate_dict(self, obj: dict) -> BasicAuth:
        """REQUIRED
        Validate a dictionary and convert it to a BasicAuth object.

        Args:
            obj: The dictionary to validate and convert.

        Returns:
            The BasicAuth object converted from the dictionary.
        """
        try:
            return BasicAuth.model_validate(obj)
        except ValidationError as e:
            raise UtcpSerializerValidationError(f"Invalid BasicAuth: {e}") from e
        except Exception as e:
            raise UtcpSerializerValidationError("An unexpected error occurred during BasicAuth validation.") from e
