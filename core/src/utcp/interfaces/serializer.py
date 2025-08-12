from abc import ABC
from typing import TypeVar, Generic

T = TypeVar('T')

class Serializer(ABC, Generic[T]):
    def to_dict(self, obj: T) -> dict:
        pass

    def validate_dict(self, obj: dict) -> T:
        pass
