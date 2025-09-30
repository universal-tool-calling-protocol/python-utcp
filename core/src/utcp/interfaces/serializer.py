from abc import ABC, abstractmethod
from typing import TypeVar, Generic
from utcp.plugins.plugin_loader import ensure_plugins_initialized

T = TypeVar('T')

class Serializer(ABC, Generic[T]):
    """REQUIRED
    Abstract interface for serializers.

    Defines the contract for serializers that convert objects to and from
    dictionaries for storage or transmission. Serializers are responsible for:
    - Converting objects to dictionaries for storage or transmission
    - Converting dictionaries back to objects
    - Ensuring data consistency during serialization and deserialization
    """

    def __init__(self):
        ensure_plugins_initialized()

    @abstractmethod
    def validate_dict(self, obj: dict) -> T:
        """REQUIRED
        Validate a dictionary and convert it to an object.

        Args:
            obj: The dictionary to validate and convert.

        Returns:
            The object converted from the dictionary.
        """
        pass

    @abstractmethod
    def to_dict(self, obj: T) -> dict:
        """REQUIRED
        Convert an object to a dictionary.

        Args:
            obj: The object to convert.

        Returns:
            The dictionary converted from the object.
        """
        pass

    def copy(self, obj: T) -> T:
        """REQUIRED
        Create a copy of an object.

        Args:
            obj: The object to copy.

        Returns:
            A copy of the object.
        """
        return self.validate_dict(self.to_dict(obj))
