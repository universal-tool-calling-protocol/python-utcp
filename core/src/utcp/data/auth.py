"""Authentication schemes for UTCP providers.

This module defines the authentication models supported by UTCP providers,
including API key authentication, basic authentication, and OAuth2.
"""

from abc import ABC
from pydantic import BaseModel
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class Auth(BaseModel, ABC):
    """Authentication details for a provider.

    Attributes:
        auth_type: The authentication type identifier.
    """
    auth_type: str

class AuthSerializer(Serializer[Auth]):
    auth_serializers: dict[str, Serializer[Auth]] = {}

    def to_dict(self, obj: Auth) -> dict:
        return AuthSerializer.auth_serializers[obj.auth_type].to_dict(obj)
    
    def validate_dict(self, obj: dict) -> Auth:
        try:
            return AuthSerializer.auth_serializers[obj["auth_type"]].validate_dict(obj)
        except KeyError:
            raise ValueError(f"Invalid auth type: {obj['auth_type']}")
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid Auth: " + traceback.format_exc()) from e
