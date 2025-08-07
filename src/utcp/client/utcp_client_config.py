"""Configuration models for UTCP client setup.

This module defines the configuration classes and variable loading mechanisms
for UTCP clients. It provides flexible variable substitution support through
multiple sources including environment files, direct configuration, and
custom variable loaders.

The configuration system enables:
    - Variable substitution in provider configurations
    - Multiple variable sources with hierarchical resolution
    - Environment file loading (.env files)
    - Direct variable specification
    - Custom variable loader implementations
"""

from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Annotated, Union, Literal
from dotenv import dotenv_values

class UtcpVariableNotFound(Exception):
    """Exception raised when a required variable cannot be found.

    This exception is thrown during variable substitution when a referenced
    variable cannot be resolved through any of the configured variable sources.
    It provides information about which variable was missing to help with
    debugging configuration issues.

    Attributes:
        variable_name: The name of the variable that could not be found.
    """
    variable_name: str

    def __init__(self, variable_name: str):
        """Initialize the exception with the missing variable name.

        Args:
            variable_name: Name of the variable that could not be found.
        """
        self.variable_name = variable_name
        super().__init__(f"Variable {variable_name} referenced in provider configuration not found. Please add it to the environment variables or to your UTCP configuration.")

class UtcpVariablesConfig(BaseModel, ABC):
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

class UtcpDotEnv(UtcpVariablesConfig):
    """Environment file variable loader implementation.

    Loads variables from .env files using the dotenv format. This loader
    supports the standard key=value format with optional quoting and
    comment support provided by the python-dotenv library.

    Attributes:
        env_file_path: Path to the .env file to load variables from.

    Example:
        ```python
        loader = UtcpDotEnv(env_file_path=".env")
        api_key = loader.get("API_KEY")
        ```
    """
    type: Literal["dotenv"] = "dotenv"
    env_file_path: str

    def get(self, key: str) -> Optional[str]:
        """Load a variable from the configured .env file.

        Args:
            key: Variable name to retrieve from the environment file.

        Returns:
            Variable value if found in the file, None otherwise.
        """
        return dotenv_values(self.env_file_path).get(key)

UtcpVariablesConfigUnion = Annotated[
    Union[
        UtcpDotEnv
    ],
    Field(discriminator="type")
]

class UtcpClientConfig(BaseModel):
    """Configuration model for UTCP client setup.

    Provides comprehensive configuration options for UTCP clients including
    variable definitions, provider file locations, and variable loading
    mechanisms. Supports hierarchical variable resolution with multiple
    sources.

    Variable Resolution Order:
        1. Direct variables dictionary
        2. Custom variable loaders (in order)
        3. Environment variables

    Attributes:
        variables: Direct variable definitions as key-value pairs.
            These take precedence over other variable sources.
        providers_file_path: Optional path to a file containing provider
            configurations. Supports JSON and YAML formats.
        load_variables_from: List of variable loaders to use for
            variable resolution. Loaders are consulted in order.

    Example:
        ```python
        config = UtcpClientConfig(
            variables={"API_BASE": "https://api.example.com"},
            providers_file_path="providers.yaml",
            load_variables_from=[
                UtcpDotEnv(env_file_path=".env")
            ]
        )
        ```
    """
    variables: Optional[Dict[str, str]] = Field(default_factory=dict)
    providers_file_path: Optional[str] = None
    load_variables_from: Optional[List[UtcpVariablesConfigUnion]] = None
