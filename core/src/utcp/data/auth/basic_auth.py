from utcp.data.auth import Auth
from utcp.interfaces.serializer import Serializer
from pydantic import Field
from typing import Literal
from utcp.exceptions import UtcpSerializerValidationError

class BasicAuth(Auth):
    """Authentication using HTTP Basic Authentication.

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
    def to_dict(self, obj: BasicAuth) -> dict:
        return obj.model_dump()
    
    def validate_dict(self, obj: dict) -> BasicAuth:
        try:
            return BasicAuth.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid BasicAuth: " + str(e))
