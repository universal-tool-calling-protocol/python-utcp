"""Authentication schemes for UTCP providers.

This module defines the authentication models supported by UTCP providers,
including API key authentication, basic authentication, and OAuth2.
"""

from pydantic import BaseModel
from utcp.interfaces.serializer import Serializer

class Auth(BaseModel):
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
        return AuthSerializer.auth_serializers[obj["auth_type"]].validate_dict(obj)
