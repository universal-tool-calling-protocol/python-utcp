from utcp.data.auth import Auth
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
from pydantic import Field, ValidationError
from typing import Literal, Optional


class OAuth2Auth(Auth):
    """REQUIRED
    Authentication using OAuth2 client credentials flow.

    Implements the OAuth2 client credentials grant type for machine-to-machine
    authentication. The client automatically handles token acquisition and refresh.

    Attributes:
        auth_type: The authentication type identifier, always "oauth2".
        token_url: The URL endpoint to fetch the OAuth2 access token from. Recommended to use injected variables.
        client_id: The OAuth2 client identifier. Recommended to use injected variables.
        client_secret: The OAuth2 client secret. Recommended to use injected variables.
        scope: Optional scope parameter to limit the access token's permissions.
    """

    auth_type: Literal["oauth2"] = "oauth2"
    token_url: str = Field(..., description="The URL to fetch the OAuth2 token from.")
    client_id: str = Field(..., description="The OAuth2 client ID.")
    client_secret: str = Field(..., description="The OAuth2 client secret.")
    scope: Optional[str] = Field(None, description="The OAuth2 scope.")


class OAuth2AuthSerializer(Serializer[OAuth2Auth]):
    """REQUIRED
    Serializer for OAuth2Auth model."""
    def to_dict(self, obj: OAuth2Auth) -> dict:
        """REQUIRED
        Convert an OAuth2Auth object to a dictionary.

        Args:
            obj: The OAuth2Auth object to convert.

        Returns:
            The dictionary converted from the OAuth2Auth object.
        """
        return obj.model_dump()
    
    def validate_dict(self, obj: dict) -> OAuth2Auth:
        """REQUIRED
        Validate a dictionary and convert it to an OAuth2Auth object.

        Args:
            obj: The dictionary to validate and convert.

        Returns:
            The OAuth2Auth object converted from the dictionary.
        """
        try:
            return OAuth2Auth.model_validate(obj)
        except ValidationError as e:
            raise UtcpSerializerValidationError(f"Invalid OAuth2Auth: {e}") from e
        except Exception as e:
            raise UtcpSerializerValidationError("An unexpected error occurred during OAuth2Auth validation.") from e
