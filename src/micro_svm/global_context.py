from typing import Callable, final

from .cfg import ProgramVisualiser
from .compiler import CompilerContext
from .descriptors import FunctionInfo, VariableInfo, structure_member_to_signature
from .types import FieldInfo, InitializerValueType, StructureTypeInfo, TypeInfo


@final
class GlobalContext:
    def __init__(self):
        self.global_variables: dict[str, VariableInfo] = {}
        self.functions: dict[str, FunctionInfo] = {}
        self.other_symbols: dict[str, VariableInfo] = {}
        self.structures: dict[str, StructureTypeInfo] = {}


    def get_symbol(self, name: str) -> VariableInfo:
        return self.global_variables[name] if name in self.global_variables else self.other_symbols[name]


    def get_field_type(self, struct: str, field: str) -> TypeInfo:
        return self.structures[struct].fields[field].type


    def get_method_info(self, structure: str, method: str) -> FunctionInfo:
        return self.functions[structure_member_to_signature(structure, method)]


    def register_symbol(self, var: VariableInfo) -> None:
        self.other_symbols[var.name] = var


    def register_function_symbols(self, func: FunctionInfo) -> None:
        if func.implementation is not None:
            for pname, ptype in func.parameters.items():
                pname = func.get_full_parameter_name(pname)
                self.register_symbol(VariableInfo(pname, ptype))
            for variable in func.implementation.local_variables:
                self.register_symbol(variable)
            if func.result_type:
                rname = func.get_full_parameter_name(FunctionInfo.RESULT_NAME)
                rtype = func.result_type
                self.register_symbol(VariableInfo(rname, rtype))


    def register_global_variable(self,
                                 name: str,
                                 type: TypeInfo,
                                 *,
                                 initializer: InitializerValueType = None,
                                 tags: set[str] | None = None) -> None:
        tags = tags if tags is not None else set()
        self.global_variables[name] = VariableInfo(name, type, initializer, tags)


    def register_function(self,
                          name: str,
                          parameters: list[tuple[str, TypeInfo]],
                          result: TypeInfo | None,
                          implementation: Callable[[CompilerContext], None] | None = None,
                          *,
                          tags: set[str] | None = None,
                          structure: str | None = None,
                          static: bool = False) -> None:
        original_name = name
        if structure is None:
            static = True
        else:
            name = structure_member_to_signature(structure, original_name)
            if static:
                self.structures[structure].static_methods[original_name] = name
            else:
                self.structures[structure].methods[original_name] = name

        func = self.functions[name] = FunctionInfo(
            original_name,
            structure,
            dict(parameters),
            result,
            static,
            set() if tags is None else tags
        )

        if implementation is not None:
            c = CompilerContext(func)
            try:
                implementation(c)
            except Exception as e:
                raise SyntaxError(f"Unable to compile function '{func}'.\nReason: {e}")
            func.implementation = c.build()
            self.register_function_symbols(func)


    def register_structure(
            self,
            name: str,
            parents: list[str] | None = None,
            fields: list[FieldInfo] | None = None
            ) -> None:
        parents = [] if parents is None else parents
        fields = [] if fields is None else fields

        sinfo = StructureTypeInfo(name, parents)
        self.structures[name] = sinfo
        for field in fields:
            sinfo.fields[field.name] = field




CONTEXT = GlobalContext()


def show_compiled_specs(spec: GlobalContext):
    v = ProgramVisualiser()

    for variable in spec.global_variables.values():
        v.simple(f"{variable} = {variable.initializer!r}")
    print()

    def show_function(func: FunctionInfo) -> None:
        for tag in sorted(func.tags):
            v.simple(f"@{tag}")
        impl = None if func.implementation is None else func.implementation.entry_node
        v.show(str(func), impl)
        print()

    for func in spec.functions.values():
        if func.structure is None:
            show_function(func)
            print()

    for struct in spec.structures.values():
        # header
        suffix = ''
        if len(struct.parents) > 0:
            suffix = ', '.join([repr(p) for p in struct.parents])
            suffix = f" extends {suffix}"
        v.simple(f"struct {struct.structure_name!r}{suffix}:")

        # body
        v.update_indentation(+1)

        for field in struct.fields.values():
            v.simple(f"{field.name}: {field.type}")

        print()
        for func_sig in struct.methods.values():
            show_function(spec.functions[func_sig])

        print()
        for func_sig in struct.static_methods.values():
            show_function(spec.functions[func_sig])

        v.update_indentation(-1)

        print()

