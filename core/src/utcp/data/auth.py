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
    """REQUIRED
    Authentication details for a provider.

    Attributes:
        auth_type: The authentication type identifier.
    """
    auth_type: str

class AuthSerializer(Serializer[Auth]):
    """REQUIRED
    Serializer for authentication details.

    Defines the contract for serializers that convert authentication details to and from
    dictionaries for storage or transmission. Serializers are responsible for:
    - Converting authentication details to dictionaries for storage or transmission
    - Converting dictionaries back to authentication details
    - Ensuring data consistency during serialization and deserialization
    """
    auth_serializers: dict[str, Serializer[Auth]] = {}

    def to_dict(self, obj: Auth) -> dict:
        """REQUIRED
        Convert an Auth object to a dictionary.

        Args:
            obj: The Auth object to convert.

        Returns:
            The dictionary converted from the Auth object.
        """
        return AuthSerializer.auth_serializers[obj.auth_type].to_dict(obj)
    
    def validate_dict(self, obj: dict) -> Auth:
        """REQUIRED
        Validate a dictionary and convert it to an Auth object.

        Args:
            obj: The dictionary to validate and convert.

        Returns:
            The Auth object converted from the dictionary.
        """
        try:
            return AuthSerializer.auth_serializers[obj["auth_type"]].validate_dict(obj)
        except KeyError:
            raise ValueError(f"Invalid auth type: {obj['auth_type']}")
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid Auth: " + traceback.format_exc()) from e
