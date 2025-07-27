from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal, TypedDict
from dotenv import dotenv_values

class UtcpVariableNotFound(Exception):
    variable_name: str

    def __init__(self, variable_name: str):
        self.variable_name = variable_name
        super().__init__(f"Variable {variable_name} referenced in provider configuration not found. Please add it to the environment variables or to your UTCP configuration.")

class UtcpVariablesConfig(BaseModel, ABC):
    type: Literal["dotenv"] = "dotenv"

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        pass

class UtcpDotEnv(UtcpVariablesConfig):
    env_file_path: str

    def get(self, key: str) -> Optional[str]:
        return dotenv_values(self.env_file_path).get(key)

class UtcpClientConfig(BaseModel):
    variables: Optional[Dict[str, str]] = Field(default_factory=dict)
    providers_file_path: Optional[str] = None
    load_variables_from: Optional[List[UtcpVariablesConfig]] = None
