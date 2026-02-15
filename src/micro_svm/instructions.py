from typing import final
from enum import Enum, auto

from .types import *



class Instruction:
    __slots__ = tuple()

    def __init__(self) -> None:
        raise AssertionError('this-should-not-be-called')

    def __str__(self) -> str:
        return self.__class__.__name__



@final
class Noop(Instruction):
    """
    A dummy instruction for testing purposes.
    """
    __slots__ = ('comment',)

    def __init__(self, comment: str | None = None):
        self.comment = comment

    def __str__(self) -> str:
        ending = '' if self.comment is None else f" [comment={repr(self.comment)}]"
        return f"{self.__class__.__name__}{ending}"



@final
class ControlPoint(Instruction):
    """
    Force check if the path is executable so far to this point.
    """
    __slots__ = ('control_id',)

    def __init__(self, control_id: int | str):
        assert control_id
        self.control_id = control_id

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [id={repr(self.control_id)}]"



@final
class PushPrimitive(Instruction):
    """
    Place a primitive value onto the stack.
    """
    __slots__ = ('value', 'type')

    def __init__(self, value: object, type: PrimitiveTypeInfo) -> None:
        assert isinstance(value, (str, int, float)) and type
        self.value = value
        self.type = type

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [value={repr(self.value)} ({self.type})]"



@final
class PushSymbolic(Instruction):
    """
    Place a symbolic primitive value onto the stack.
    """
    __slots__ = ('type',)

    def __init__(self, type: PrimitiveTypeInfo) -> None:
        assert type and type.is_primitive()
        self.type = type

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [type={self.type}]"



@final
class Pop(Instruction):
    """
    Remove a single <u>item</u> from the top of the execution stack.

    *Can be useful for discarding return value or removing boundary objects.*
    """
    __slots__ = tuple()

    def __init__(self) -> None:
        pass



@final
class SubroutineEnter(Instruction):
    """
    A marker instruction.
    """
    __slots__ = tuple()

    def __init__(self) -> None:
        pass



@final
class SubroutineExit(Instruction):
    """
    A marker instruction.
    """
    __slots__ = tuple()

    def __init__(self) -> None:
        pass



@final
class VariableRead(Instruction):
    """
    Read a value from a variable and place its value, as expression, onto the stack.
    """
    __slots__ = ('source_name', 'source_is_local')

    def __init__(self, src: str, local: bool) -> None:
        assert src
        self.source_name = src
        self.source_is_local = local

    def __str__(self) -> str:
        flag = 'local' if self.source_is_local else 'global'
        return f"{self.__class__.__name__} [src={self.source_name} ({flag})]"



@final
class VariableWrite(Instruction):
    """
    Write a new value to a variable.
    The value is being pulled from the top of the execution stack.
    """
    __slots__ = ('destination_name', 'destination_is_local')

    def __init__(self, dst: str, local: bool) -> None:
        assert dst
        self.destination_name = dst
        self.destination_is_local = local

    def __str__(self) -> str:
        flag = 'local' if self.destination_is_local else 'global'
        return f"{self.__class__.__name__} [dst={self.destination_name} ({flag})]"


class PrimitiveOps(Enum):
    ADD     = auto(), 2  # a + b
    SUB     = auto(), 2  # a - b
    MUL     = auto(), 2  # a * b
    DIV     = auto(), 2  # a / b
    MOD     = auto(), 2  # a % b
    AND     = auto(), 2  # a & b
    OR      = auto(), 2  # a | b
    XOR     = auto(), 2  # a ^ b
    SHR     = auto(), 2  # a >> b
    SHL     = auto(), 2  # a << b
    EQ      = auto(), 2  # a == b
    NEQ     = auto(), 2  # a != b
    LESS    = auto(), 2  # a < b
    LEQ     = auto(), 2  # a <= b
    GREATER = auto(), 2  # a > b
    GEQ     = auto(), 2  # a >= b
    NEGATE  = auto(), 1  # -a
    NOT     = auto(), 1  # ~a
    ABS     = auto(), 1  # |a|
    MAX     = auto(), 2  # max(a, b)
    MIN     = auto(), 2  # min(a, b)
    FLOOR   = auto(), 1  # floor(a)

    def get_input_count(self) -> int:
        return self.value[1]


@final
class PrimitiveOp(Instruction):
    """
    Perform a N-nary operation on N values, pulled from the top of the stack, and place the result back on top.
    """
    __slots__ = ('operation', 'input_count')

    def __init__(self, op: PrimitiveOps) -> None:
        assert op is not None
        self.operation = op
        self.input_count = op.get_input_count()

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [op={self.operation.name}, inputs={self.input_count}]"



@final
class Assume(Instruction):
    """
    Make an assumption that the argument, pulled from the top of the stack, is equal to True.
    """
    __slots__ = tuple()

    def __init__(self) -> None:
        pass



@final
class ContainerGetSize(Instruction):
    """
    Read the current size of the container.
    The container reference will be pulled from the top of the execution stack.
    The result will be placed back on top of the stack.
    """
    __slots__ = tuple()

    def __init__(self):
        pass



@final
class ArrayOps(Enum):
    NEW          = auto(), 1  # size
    SET_SIZE     = auto(), 2  # ref, size
    GET          = auto(), 2  # ref, index
    SET          = auto(), 3  # ref, index, value
    COPY         = auto(), 5  # src, src_index, dst, dst_index, count
    EQUALS_RANGE = auto(), 5  # a, a_index, b, b_index, count

    def get_input_count(self) -> int:
        return self.value[1]


@final
class ArrayOperation(Instruction):
    """
    Perform an operation on a 1D array.
    """
    __slots__ = ('operation', 'item_type')

    def __init__(self, op: ArrayOps, item_type: PrimitiveTypeInfo):
        assert op is not None
        assert item_type is None or item_type.is_primitive()
        self.operation = op
        self.item_type = item_type

    def __str__(self):
        return f"{self.__class__.__name__} [op={self.operation.name}, type={self.item_type}]"



@final
class SetOps(Enum):
    NEW          = auto(), 0
    CONTAINS     = auto(), 2  # ref, item
    ANY_ITEM     = auto(), 1  # ref
    ADD          = auto(), 2  # ref, item
    REMOVE       = auto(), 2  # ref, item
    UNION        = auto(), 2  # in_a, in_b, out_c
    INTERSECTION = auto(), 2  # in_a, in_b, out_c
    EQUALS       = auto(), 2  # in_a, in_b

    def get_input_count(self) -> int:
        return self.value[1]


@final
class SetOperation(Instruction):
    """
    Perform an operation on a "set" container object.
    """
    __slots__ = ('operation', 'item_type')

    def __init__(self, op: SetOps, item_type: PrimitiveTypeInfo):
        assert op is not None
        assert item_type.is_primitive()
        self.operation = op
        self.item_type = item_type

    def __str__(self):
        return f"{self.__class__.__name__} [op={self.operation.name}, type={self.item_type}]"



@final
class MapOps(Enum):
    NEW          = auto(), 0
    GET          = auto(), 2  # ref, key
    SET          = auto(), 3  # ref, key, value
    REMOVE       = auto(), 2  # ref, key
    HAS_KEY      = auto(), 2  # ref, key
    HAS_VALUE    = auto(), 2  # ref, value
    HAS_PAIR     = auto(), 3  # ref, key, value
    ANY_KEY      = auto(), 1  # ref
    ANY_VALUE    = auto(), 1  # ref
    UNION        = auto(), 2  # in_a, in_b, out_c
    INTERSECTION = auto(), 2  # in_a, in_b, out_c
    EQUALS       = auto(), 2  # in_a, in_b

    def get_input_count(self) -> int:
        return self.value[1]


@final
class MapOperation(Instruction):
    """
    Perform an operation on a "map" container object.
    """
    __slots__ = ('operation', 'kv_type')

    def __init__(self, op: MapOps, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]):
        assert op is not None
        assert kv_type[0].is_primitive()
        assert kv_type[1].is_primitive()
        self.operation = op
        self.kv_type = kv_type

    def __str__(self):
        return f"{self.__class__.__name__} [op={self.operation.name}, type={self.kv_type[0]}:{self.kv_type[1]}]"



@final
class TransformOps(Enum):
    NEW = auto(), 0
    GET = auto(), 2  # ref, key
    SET = auto(), 3  # ref, key, value

    def get_input_count(self) -> int:
        return self.value[1]


@final
class TransformOperation(Instruction):
    """
    Perform an operation on a "transform" container-like object.
    """
    __slots__ = ('operation', 'kv_type')

    def __init__(self, op: TransformOps, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]):
        assert op is not None
        assert kv_type[0].is_primitive()
        assert kv_type[1].is_primitive()
        self.operation = op
        self.kv_type = kv_type

    def __str__(self):
        return f"{self.__class__.__name__} [op={self.operation.name}, type={self.kv_type[0]}:{self.kv_type[1]}]"



@final
class NewInstance(Instruction):
    """
    Create a new object of a given class.
    Reference to the newly created instance will be placed on top of the execution stack.
    """
    __slots__ = ('structure_name',)

    def __init__(self, structure_name: str):
        assert structure_name
        self.structure_name = structure_name

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [type={self.structure_name}]"



@final
class FreeInstance(Instruction):
    """
    Mark an object instance as "freed". An object cannot be "freed" more than once.
    Reference to the instance will be pulled from the top of the execution stack.
    """
    __slots__ = tuple()

    def __init__(self):
        pass



@final
class Copy(Instruction):
    """
    Makes N copies of a value from the X'th position of the execution STACK (starting from the top) putting them back on top.
    """
    __slots__ = ('number_of_copies', 'stack_position')

    def __init__(self, *, count: int = 1, index: int = 0) -> None:
        assert count > 0
        self.number_of_copies = count
        self.stack_position = index

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [count={self.number_of_copies}, pos={self.stack_position}]"



@final
class FieldRead(Instruction):
    """
    Read a value from a field of an object's instance given a reference on the top of the stack.
    Place the acquired value, as expression, back onto the stack.
    """
    __slots__ = ('source_structure_name', 'source_field_name')

    def __init__(self, struct: str, field: str) -> None:
        assert struct and field
        self.source_structure_name = struct
        self.source_field_name = field

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [src={self.source_structure_name}.{self.source_field_name}]"



@final
class FieldWrite(Instruction):
    """
    Write a new value to an object's instance field given a reference.
    The value and a reference are being pulled from the top of the execution stack.
    """
    __slots__ = ('destination_structure_name', 'destination_field_name')

    def __init__(self, struct: str, field: str) -> None:
        assert struct and field
        self.destination_structure_name = struct
        self.destination_field_name = field

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [dst={self.destination_structure_name}.{self.destination_field_name}]"



@final
class InstanceOf(Instruction):
    """
    Checks if a given reference to an object is an instance of a specified class (or a subclass).
    The reference is pulled from the top of the stack.
    The result is placed back on top.
    """
    __slots__ = ('expected_structure_name', 'exact_match')

    def __init__(self, struct: str, *, exact: bool = False) -> None:
        assert struct
        self.expected_structure_name = struct
        self.exact_match = exact

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [struct={self.expected_structure_name}, exact={self.exact_match}]"



@final
class SimpleDiff(Instruction):
    """
    Compares two values and returns "0" if they are equal and "1" otherwise.
    The values to compare are pulled from the top of the execution stack.
    The result is placed back on top.
    """
    __slots__ = ('result_type',)

    def __init__(self, type: PrimitiveTypeInfo) -> None:
        assert type is not None
        self.result_type = type

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [type={self.result_type}]"



@final
class DistinctValues(Instruction):
    """
    Compare N values and return a boolean value indicating whether all values are distinct.
    The values to compare are pulled from the top of the execution stack.
    The result is placed back on top.
    """
    __slots__ = ('value_count',)

    def __init__(self, value_count: int):
        assert value_count >= 1
        self.value_count = value_count

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [count={self.value_count}]"



@final
class FaultStatusRead(Instruction):
    """
    Read the current global "safeguard fault" machine status.
    The result (boolean) is placed on top of the execution stack.
    """
    __slots__ = tuple()

    def __init__(self):
        pass



@final
class FaultStatusClear(Instruction):
    """
    Reset the current global "safeguard fault" machine status to "false".
    """
    __slots__ = tuple()

    def __init__(self):
        pass



@final
class ExceptionRead(Instruction):
    """
    Read last thrown exception object reference.
    If no exception is currently active, this instruction will push a "null" reference onto the stack.
    """
    __slots__ = tuple()

    def __init__(self):
        pass



@final
class ExceptionWrite(Instruction):
    """
    Set last thrown exception object reference to a given reference.
    The new reference is pulled from the top of the execution stack.
    """
    __slots__ = tuple()

    def __init__(self):
        pass



@final
class StackBoundary:
    __slots__ = tuple()

    def __str__(self) -> str:
        return f"<stack-boundary#{id(self):016x}>"


@final
class ClearStackToBoundary(Instruction):
    """
    Clear the execution stack up to the specified stack boundary.

    **Warning:** the boundary object is compared against stack elements using the "is" operator!
    """
    __slots__ = ('boundary',)

    def __init__(self, boundary: StackBoundary | None):
        self.boundary = boundary



@final
class PushStackBoundary(Instruction):
    """
    Push a new boundary object onto the execution stack.
    """
    __slots__ = ('boundary',)

    def __init__(self, boundary: StackBoundary):
        assert isinstance(boundary, StackBoundary)
        self.boundary = boundary



@final
class StringOps(Enum):
    LENGTH        = auto(), 1  # str
    CONCAT        = auto(), 2  # strA, strB
    CONTAINS      = auto(), 2  # str, sub
    INDEX_OF      = auto(), 3  # str, sub, offset
    LAST_INDEX_OF = auto(), 2  # str, sub
    STARTS_WITH   = auto(), 2  # str, prefix
    ENDS_WITH     = auto(), 2  # str, suffix
    COPY          = auto(), 2  # str, offset, count
    REPLACE_ONCE  = auto(), 3  # str, old, new
    INT_TO_STR    = auto(), 1  # value
    STR_TO_INT    = auto(), 1  # value
    ORD           = auto(), 1  # value

    def get_input_count(self) -> int:
        return self.value[1]


@final
class StringOperation(Instruction):
    """
    Perform an operation with strings.
    """
    __slots__ = ('operation',)

    def __init__(self, op: StringOps):
        assert op is not None
        self.operation = op

    def __str__(self):
        return f"{self.__class__.__name__} [op={self.operation.name}]"





@final
class InstructionResolver:
    __slots__ = ('visitor', 'prefix')

    def __init__(self, visitor: object, *, prefix: str = 'visit_instruction_') -> None:
        assert visitor is not None
        assert prefix is not None
        self.visitor = visitor
        self.prefix = prefix

    def visit(self, ins: Instruction) -> None:
        name = self.prefix + ins.__class__.__name__
        if (method := getattr(self.visitor, name, None)) is not None:
            method(ins)
        else:
            raise AssertionError(f"Unable to find method '{name}' in visitor")


