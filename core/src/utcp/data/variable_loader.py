from abc import ABC, abstractmethod
from dotenv import dotenv_values
from pydantic import BaseModel
from typing import Optional, Dict, Type
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError

class VariableLoader(BaseModel, ABC):
    """Abstract base class for variable loading configurations.

    Defines the interface for variable loaders that can retrieve variable
    values from different sources such as files, databases, or external
    services. Implementations provide specific loading mechanisms while
    maintaining a consistent interface.

    Attributes:
        type: Type identifier for the variable loader.
    """
    type: str

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """Retrieve a variable value by key.

        Args:
            key: Variable name to retrieve.

        Returns:
            Variable value if found, None otherwise.
        """
        pass

class VariableLoaderSerializer(Serializer[VariableLoader]):
    """Custom serializer for VariableLoader model."""
    loader_serializers: Dict[str, Type[Serializer[VariableLoader]]] = {}
    
    def to_dict(self, obj: VariableLoader) -> dict:
        return VariableLoaderSerializer.loader_serializers[obj.type].to_dict(obj)
    
    def validate_dict(self, data: dict) -> VariableLoader:
        try:
            return VariableLoaderSerializer.loader_serializers[data["type"]].validate_dict(data)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid VariableLoader: " + str(e))
