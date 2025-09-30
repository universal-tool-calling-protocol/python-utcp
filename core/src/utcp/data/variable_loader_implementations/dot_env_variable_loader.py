from utcp.data.variable_loader import VariableLoader
from typing import Optional, Literal
from dotenv import dotenv_values
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class DotEnvVariableLoader(VariableLoader):
    """REQUIRED
    Environment file variable loader implementation.

    Loads variables from .env files using the dotenv format. This loader
    supports the standard key=value format with optional quoting and
    comment support provided by the python-dotenv library.

    Attributes:
        env_file_path: Path to the .env file to load variables from.

    Example:
        ```python
        loader = DotEnvVariableLoader(env_file_path=".env")
        api_key = loader.get("API_KEY")
        ```
    """
    variable_loader_type: Literal["dotenv"] = "dotenv"
    env_file_path: str

    def get(self, key: str) -> Optional[str]:
        """REQUIRED
        Load a variable from the configured .env file.

        Args:
            key: Variable name to retrieve from the environment file.

        Returns:
            Variable value if found in the file, None otherwise.
        """
        return dotenv_values(self.env_file_path).get(key)

class DotEnvVariableLoaderSerializer(Serializer[DotEnvVariableLoader]):
    """REQUIRED
    Serializer for DotEnvVariableLoader model."""
    def to_dict(self, obj: DotEnvVariableLoader) -> dict:
        """REQUIRED
        Convert a DotEnvVariableLoader object to a dictionary.

        Args:
            obj: The DotEnvVariableLoader object to convert.

        Returns:
            The dictionary converted from the DotEnvVariableLoader object.
        """
        return obj.model_dump()
    
    def validate_dict(self, data: dict) -> DotEnvVariableLoader:
        """REQUIRED
        Validate a dictionary and convert it to a DotEnvVariableLoader object.

        Args:
            data: The dictionary to validate and convert.

        Returns:
            The DotEnvVariableLoader object converted from the dictionary.
        """
        try:
            return DotEnvVariableLoader.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid DotEnvVariableLoader: " + traceback.format_exc()) from e
