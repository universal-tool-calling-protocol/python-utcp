from utcp.data.auth import Auth
from utcp.interfaces.serializer import Serializer
from pydantic import Field, ValidationError
from typing import Literal
from utcp.exceptions import UtcpSerializerValidationError

class ApiKeyAuth(Auth):
    """REQUIRED
    Authentication using an API key.

    The key can be provided directly or sourced from an environment variable.
    Supports placement in headers, query parameters, or cookies.

    Attributes:
        auth_type: The authentication type identifier, always "api_key".
        api_key: The API key for authentication. Values starting with '$' or formatted as '${}' are
            treated as an injected variable from environment or configuration.
        var_name: The name of the header, query parameter, or cookie that
            contains the API key.
        location: Where to include the API key (header, query parameter, or cookie).
    """

    auth_type: Literal["api_key"] = "api_key"
    api_key: str = Field(..., description="The API key for authentication. Values starting with '$' or formatted as '${}' are treated as an injected variable from environment or configuration. This is the recommended way to provide API keys.")
    var_name: str = Field(
        "X-Api-Key", description="The name of the header, query parameter, cookie or other container for the API key."
    )
    location: Literal["header", "query", "cookie"] = Field(
        "header", description="Where to include the API key (header, query parameter, or cookie)."
    )


class ApiKeyAuthSerializer(Serializer[ApiKeyAuth]):
    """REQUIRED
    Serializer for ApiKeyAuth model."""
    def to_dict(self, obj: ApiKeyAuth) -> dict:
        """REQUIRED
        Convert an ApiKeyAuth object to a dictionary.

        Args:
            obj: The ApiKeyAuth object to convert.

        Returns:
            The dictionary converted from the ApiKeyAuth object.
        """
        return obj.model_dump()
    
    def validate_dict(self, obj: dict) -> ApiKeyAuth:
        """REQUIRED
        Validate a dictionary and convert it to an ApiKeyAuth object.

        Args:
            obj: The dictionary to validate and convert.

        Returns:
            The ApiKeyAuth object converted from the dictionary.
        """
        try:
            return ApiKeyAuth.model_validate(obj)
        except ValidationError as e:
            raise UtcpSerializerValidationError(f"Invalid ApiKeyAuth: {e}") from e
        except Exception as e:
            raise UtcpSerializerValidationError("An unexpected error occurred during ApiKeyAuth validation.") from e
