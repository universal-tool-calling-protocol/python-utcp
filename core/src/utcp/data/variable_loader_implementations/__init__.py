from utcp.data.variable_loader_implementations.dot_env_variable_loader import DotEnvVariableLoader, DotEnvVariableLoaderSerializer
from utcp.discovery import register_variable_loader

register_variable_loader("dotenv", DotEnvVariableLoaderSerializer())

__all__ = [
    "DotEnvVariableLoader",
    "DotEnvVariableLoaderSerializer",
]
