from abc import ABC, abstractmethod
from dotenv import dotenv_values
from pydantic import BaseModel
from typing import Optional, Dict, Type
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class VariableLoader(BaseModel, ABC):
    """Abstract base class for variable loading configurations.

    Defines the interface for variable loaders that can retrieve variable
    values from different sources such as files, databases, or external
    services. Implementations provide specific loading mechanisms while
    maintaining a consistent interface.

    Attributes:
        variable_loader_type: Type identifier for the variable loader.
    """
    variable_loader_type: str

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
        return VariableLoaderSerializer.loader_serializers[obj.variable_loader_type].to_dict(obj)
    
    def validate_dict(self, data: dict) -> VariableLoader:
        try:
            return VariableLoaderSerializer.loader_serializers[data["variable_loader_type"]].validate_dict(data)
        except KeyError:
            raise ValueError(f"Invalid variable loader type: {data['variable_loader_type']}")
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid VariableLoader: " + traceback.format_exc()) from e
