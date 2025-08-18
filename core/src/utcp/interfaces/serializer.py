from abc import ABC, abstractmethod
from typing import TypeVar, Generic
from utcp.plugins.plugin_loader import ensure_plugins_initialized

T = TypeVar('T')

class Serializer(ABC, Generic[T]):

    def __init__(self):
        ensure_plugins_initialized()

    @abstractmethod
    def validate_dict(self, obj: dict) -> T:
        pass

    @abstractmethod
    def to_dict(self, obj: T) -> dict:
        pass

    def copy(self, obj: T) -> T:
        return self.validate_dict(self.to_dict(obj))
