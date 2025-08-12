from utcp.data.auth import Auth, AuthSerializer
from utcp.data.variable_loader import VariableLoader, VariableLoaderSerializer
from utcp.interfaces.serializer import Serializer

def register_auth(auth_type: str, serializer: Serializer[Auth], override: bool = False) -> bool:
    if not override and auth_type in AuthSerializer.auth_serializers:
        return False
    AuthSerializer.auth_serializers[auth_type] = serializer
    return True

def register_variable_loader(loader_type: str, serializer: Serializer[VariableLoader], override: bool = False) -> bool:
    if not override and loader_type in VariableLoaderSerializer.loader_serializers:
        return False
    VariableLoaderSerializer.loader_serializers[loader_type] = serializer
    return True
