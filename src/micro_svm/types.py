import z3
from typing import final, Callable


class TypeInfo:
    def __init__(self, name: str, z3_sort: z3.SortRef, default_value: z3.ExprRef | None) -> None:
        assert name and z3_sort is not None
        self.name = name
        self.z3_sort = z3_sort
        self.default_value = default_value

    def is_primitive(self) -> bool:
        return False

    def is_reference(self) -> bool:
        return False

    def is_collection(self) -> bool:
        return False

    def wrap_primitive(self, value: object) -> z3.ExprRef:
        raise NotImplementedError('Unsupported operation')

    def __repr__(self):
        return self.__str__()



#@final
class PrimitiveTypeInfo(TypeInfo):
    def __init__(
            self,
            name: str,
            z3_sort: z3.SortRef,
            default_raw: object,
            convertor: Callable[[object], z3.ExprRef]
    ) -> None:
        super().__init__(name, z3_sort, convertor(default_raw))
        assert convertor is not None
        self.default_raw = default_raw
        self.convertor = convertor

    def is_primitive(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.name

    def wrap_primitive(self, value: object) -> z3.ExprRef:
        return self.convertor(value)



@final
class OpaqueReferenceTypeInfo(PrimitiveTypeInfo):
    def __init__(self, name: str) -> None:
        super().__init__(name, z3.IntSort(), 0, z3.IntVal)

    def is_reference(self):
        return True



boolean   = PrimitiveTypeInfo('boolean', z3.BoolSort(),     False, z3.BoolVal)
int8      = PrimitiveTypeInfo('int8',    z3.BitVecSort(8),  0,     lambda x: z3.BitVecVal(x, 8))
int16     = PrimitiveTypeInfo('int16',   z3.BitVecSort(16), 0,     lambda x: z3.BitVecVal(x, 16))
int32     = PrimitiveTypeInfo('int32',   z3.BitVecSort(32), 0,     lambda x: z3.BitVecVal(x, 32))
int64     = PrimitiveTypeInfo('int64',   z3.BitVecSort(64), 0,     lambda x: z3.BitVecVal(x, 64))
integer   = PrimitiveTypeInfo('integer', z3.IntSort(),      0,     z3.IntVal)
real      = PrimitiveTypeInfo('real',    z3.RealSort(),     0.0,   z3.RealVal)
char      = PrimitiveTypeInfo('char',    z3.CharSort(),     '\0',  z3.CharVal)
string    = PrimitiveTypeInfo('string',  z3.StringSort(),   '',    z3.StringVal)
reference = OpaqueReferenceTypeInfo('ref')

PRIMITIVE_TYPES = [
    boolean,
    int8,
    int16,
    int32,
    int64,
    integer,
    real,
    char,
    string,
    reference,
]


@final
class ArrayTypeInfo(TypeInfo):
    def __init__(self, item_type: PrimitiveTypeInfo) -> None:
        super().__init__('array', z3.ArraySort(integer.z3_sort, item_type.z3_sort), None)
        assert item_type is not None
        self.index_type = integer
        self.item_type = item_type

    def is_collection(self) -> bool:
        return True

    def __str__(self) -> str:
        return f"{self.name}<{self.item_type}>"


def array(element_type: TypeInfo):
    return ArrayTypeInfo(element_type)



@final
class KnownReferenceTypeInfo(PrimitiveTypeInfo):
    def __init__(self, target: TypeInfo) -> None:
        super().__init__(reference.name, reference.z3_sort, reference.default_raw, reference.convertor)
        assert target is not None
        self.target_type = target
        if target.is_primitive():
            raise ValueError('References on primitives are not supported')

    def is_reference(self):
        return True

    def __str__(self) -> str:
        return f"{self.name}<{self.target_type}>"


def ref(type: TypeInfo):
    return KnownReferenceTypeInfo(type)




@final
class SetTypeInfo(TypeInfo):
    def __init__(self, item_type: PrimitiveTypeInfo):
        super().__init__('set', z3.ArraySort(item_type.z3_sort, z3.BoolSort()), None)
        assert item_type is not None
        self.item_type = item_type

    def is_collection(self) -> bool:
        return True

    def __str__(self) -> str:
        return f"{self.name}<{self.item_type}>"


def set_of(item_type: PrimitiveTypeInfo):
    return SetTypeInfo(item_type)



@final
class MapTypeInfo(TypeInfo):
    def __init__(self, key_type: PrimitiveTypeInfo, value_type: PrimitiveTypeInfo):
        super().__init__('map', z3.ArraySort(key_type.z3_sort, value_type.z3_sort, z3.BoolSort()), None)
        assert key_type is not None and value_type is not None
        self.key_type = key_type
        self.value_type = value_type
        self.kv_type = (key_type, value_type)

    def is_collection(self) -> bool:
        return True

    def __str__(self) -> str:
        return f"{self.name}<{self.key_type}, {self.value_type}>"


def map_of(key: PrimitiveTypeInfo, value: PrimitiveTypeInfo):
    return MapTypeInfo(key, value)



@final
class TransformTypeInfo(TypeInfo):
    def __init__(self, key_type: PrimitiveTypeInfo, value_type: PrimitiveTypeInfo):
        super().__init__('transform', z3.ArraySort(key_type.z3_sort, value_type.z3_sort), None)
        assert key_type is not None and value_type is not None
        self.key_type = key_type
        self.value_type = value_type
        self.kv_type = (key_type, value_type)

    def is_collection(self) -> bool:
        return False

    def __str__(self) -> str:
        return f"{self.name}<{self.key_type}, {self.value_type}>"


def transform_of(key: PrimitiveTypeInfo, value: PrimitiveTypeInfo):
    return TransformTypeInfo(key, value)



@final
class FieldInfo:
    def __init__(self, name: str, type: PrimitiveTypeInfo, tags: set[str]) -> None:
        assert name and type.is_primitive() and tags is not None
        self.name = name
        self.type = type
        self.tags = tags


def field(name: str, type: TypeInfo, *, tags: set[str] | None = None):
    return FieldInfo(name, type, set() if tags is None else tags)



@final
class StructureTypeInfo(TypeInfo):
    def __init__(self, name: str, parents: list[str]):
        super().__init__(reference.name, reference.z3_sort, reference.default_value)
        assert parents is not None
        self.structure_name = name
        self.parents = parents
        self.fields: dict[str, FieldInfo] = {}
        self.methods: dict[str, str]        = {}  # name -> full signature (directly bound)
        self.static_methods: dict[str, str] = {}  # name -> full signature (directly bound)

    def __str__(self) -> str:
        return f"struct='{self.structure_name}'"

