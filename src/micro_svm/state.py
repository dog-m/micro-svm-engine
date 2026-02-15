from dataclasses import dataclass

from .descriptors import ValueType, InitializerValueType
from .types import *


def hash_str(s: str | object) -> int:
    if not isinstance(s, str):
        s = str(s)
    h = 7
    for c in s:
        h = 31 * h + ord(c)
    return h



@dataclass
class ObjectState:
    id: str
    type: ArrayTypeInfo | SetTypeInfo | MapTypeInfo | TransformTypeInfo | StructureTypeInfo
    state: InitializerValueType

    def __hash__(self):
        return hash((
            hash_str(self.id),
            hash_str(self.type),
            hash_str(self.state),
        ))


@dataclass
class VariableState:
    name: str
    state: ValueType

    def __hash__(self):
        return hash((
            hash_str(self.name),
            hash_str(self.state),
        ))


class ProgramState:
    def __init__(self):
        self.global_variables: dict[str, VariableState] = {}
        self.expected_objects: dict[str, ObjectState] = {}
        self.objects: dict[str, ObjectState] = {}
        self.allow_object_reuse = True

    def __hash__(self):
        return hash((
            hash(tuple(self.global_variables.values())),
            hash(tuple(hash_str(k) for k in self.expected_objects.keys())),
            hash(tuple(self.objects.values())),
            self.allow_object_reuse,
        ))


