from utcp.data.variable_loader import VariableLoader
from typing import Optional, Literal
from dotenv import dotenv_values
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class DotEnvVariableLoader(VariableLoader):
    """Environment file variable loader implementation.

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
        """Load a variable from the configured .env file.

        Args:
            key: Variable name to retrieve from the environment file.

        Returns:
            Variable value if found in the file, None otherwise.
        """
        return dotenv_values(self.env_file_path).get(key)

class DotEnvVariableLoaderSerializer(Serializer[DotEnvVariableLoader]):
    def to_dict(self, obj: DotEnvVariableLoader) -> dict:
        return obj.model_dump()
    
    def validate_dict(self, data: dict) -> DotEnvVariableLoader:
        try:
            return DotEnvVariableLoader.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid DotEnvVariableLoader: " + traceback.format_exc()) from e
