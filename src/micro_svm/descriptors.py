from typing import final

from .cfg import Node
from .types import InitializerValueType, TypeInfo


@final
class VariableInfo:
    def __init__(self,
                 name: str, type: TypeInfo,
                 initializer: InitializerValueType = None,
                 tags: set[str] | None = None) -> None:
        assert name
        assert type is not None
        self.name = name
        self.type = type
        self.initializer = initializer
        self.tags: set[str] = set() if tags is None else tags

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, value: object) -> bool:
        return self.name == value.name

    def __ne__(self, value: object) -> bool:
        return self.name != value.name

    def __str__(self):
        return f"{self.name}: {self.type}"



@final
class CompiledSubroutine:
    def __init__(self, entry_node: Node, temp_variables: list[VariableInfo]):
        assert entry_node is not None
        assert temp_variables is not None
        self.entry_node = entry_node
        self.local_variables = temp_variables



def structure_member_to_signature(structure_name: str, member_name: str) -> str:
    return f"{structure_name}.{member_name}"



@final
class FunctionInfo:
    RESULT_NAME = '~result'

    def __init__(self,
                 original_name: str,
                 structure: str | None,
                 parameters: dict[str, TypeInfo],
                 result_type: TypeInfo | None,
                 is_static: bool,
                 tags: set[str]) -> None:
        assert original_name
        assert parameters is not None
        assert tags is not None
        self.structure = structure
        self.original_name = original_name
        self.full_name = original_name if structure is None else structure_member_to_signature(structure, original_name)
        self.parameters = parameters
        self.result_type = result_type
        self.is_static = is_static
        self.implementation: CompiledSubroutine | None = None
        self.tags = tags

    def get_full_parameter_name(self, name: str) -> str:
        return f"{self.full_name}#{name}"

    def __str__(self):
        prefix = '[static] ' if self.is_static else ''
        params = [f"{name}: {type}" for name, type in self.parameters.items()]
        result = 'void' if self.result_type is None else self.result_type
        return f"{prefix}{self.full_name} ({', '.join(params)}) -> {result}"




