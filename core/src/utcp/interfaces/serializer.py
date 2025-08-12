from abc import ABC, abstractmethod
from typing import TypeVar, Generic

T = TypeVar('T')

class Serializer(ABC, Generic[T]):
    @abstractmethod
    def to_dict(self, obj: T) -> dict:
        pass

    @abstractmethod
    def validate_dict(self, obj: dict) -> T:
        pass

    def copy(self, obj: T) -> T:
        return self.validate_dict(self.to_dict(obj))
