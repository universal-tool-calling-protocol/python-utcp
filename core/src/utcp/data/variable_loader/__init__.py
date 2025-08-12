from utcp.data.variable_loader.variable_loader import VariableLoader, VariableLoaderSerializer
from utcp.data.variable_loader.dot_env_variable_loader import DotEnvVariableLoader, DotEnvVariableLoaderSerializer
from utcp.discovery import register_variable_loader

register_variable_loader("dotenv", DotEnvVariableLoaderSerializer())

__all__ = [
    "VariableLoader",
    "VariableLoaderSerializer",
    "DotEnvVariableLoader",
    "DotEnvVariableLoaderSerializer",
]
