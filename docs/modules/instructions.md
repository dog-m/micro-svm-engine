# micro_svm.instructions

## Overview

### Summary

This module defines the complete instruction set for the symbolic virtual machine (SVM), providing a comprehensive collection of primitive operations for symbolic execution. It includes stack manipulation, variable access, primitive arithmetic and logical operations, container operations (arrays, sets, maps, transforms), object field access and instance management, string operations, fault and exception handling. This comprehensive instruction set enables the symbolic execution engine to model a wide variety of programming language constructs and program behaviors.

### Purpose

The `Instruction` base class and its concrete subclasses form the fundamental building blocks of program specifications in the Micro-SVM project. Each instruction represents a single atomic operation that can be executed during symbolic path exploration. The module provides both simple operations (like pushing values onto the stack or reading/writing variables) and complex operations (like comparing array segments, performing set/map operations, or checking object instance types).

### Role in the Project

The instruction set is central to the Micro-SVM's symbolic execution capabilities. Instructions are generated during the path enumeration phase (see `micro_svm.exploration`) and then executed during the path validation phase (see `micro_svm.execution`). Each instruction is dispatched to its handler via the `InstructionResolver` visitor pattern implementation, which routes the instruction to the appropriate method on the symbolic state machine.

### Contracts

- All instruction classes are marked with the `@final` decorator, indicating they should not be subclassed
- Stack manipulation instructions assume the stack has sufficient depth; insufficient depth will cause execution to crash
- Object and container operations assume valid instance references; invalid references may lead the execution to produce undesired results
- `InstructionResolver` class expects a visitor object with methods named `visit_instruction_<ClassName>` for each instruction type

## Classes

### `Instruction: ABC`

Abstract base class for all instructions in the Micro-SVM instruction set.

#### Public API

- **Methods:**
  - `__str__() -> str` - Returns the class name as default string representation for all instructions

### `Noop: Instruction`

A placeholder instruction.

#### Public API

- **Fields:**
  - `comment: str | None` - Optional comment for debugging/testing purposes

- **Methods:**
  - `__init__(comment: str | None = None)` - Creates a no-op instruction with optional comment
  - `__str__() -> str` - Returns `Noop [comment=...]`

### `ControlPoint: Instruction`

Force check if the path is executable so far to this point.

#### Public API

- **Fields:**
  - `control_id: int | str` - Identifier for the control point (should be non-zero)

- **Methods:**
  - `__init__(control_id: int | str)` - Creates a control point instruction with the given identifier
  - `__str__() -> str` - Returns `ControlPoint [id=...]`

### `PushPrimitive: Instruction`

Place a primitive value onto the stack.

#### Public API

- **Fields:**
  - `type: PrimitiveTypeInfo` - Type information for the value
  - `value: ValueType` - The primitive value to push (`bool`, `int`, `float`, or `str`)

- **Methods:**
  - `__init__(value: ValueType, type: PrimitiveTypeInfo)` - Creates a primitive push instruction
  - `__str__() -> str` - Returns `PushPrimitive [value=... (type)]`

### `PushSymbolic: Instruction`

Place a symbolic primitive value onto the stack.

#### Public API

- **Fields:**
  - `type: PrimitiveTypeInfo` - Type information for the symbolic value

- **Methods:**
  - `__init__(type: PrimitiveTypeInfo)` - Creates a symbolic push instruction
  - `__str__() -> str` - Returns `PushSymbolic [type=...]`

#### Implementation details

- Used to introduce uninterpreted symbolic variables
- The `type` **must** be a primitive type (asserted in constructor)

### `Pop: Instruction`

Remove a single item from the top of the execution stack.

#### Public API

- **Methods:**
  - `__init__()` - Creates a pop instruction

### `SubroutineEnter: Instruction`

Marker instruction for subroutine entry.

#### Public API

- **Methods:**
  - `__init__()` - Creates a subroutine enter marker

#### Implementation details

- Marks the beginning of a subroutine/function call
- Used to manage stack frame information during execution
- Works in conjunction with `SubroutineExit` to track subroutine boundaries

### `SubroutineExit: Instruction`

Marker instruction for subroutine exit.

#### Public API

- **Methods:**
  - `__init__()` - Creates a subroutine exit marker

#### Implementation details

- Marks the end of a subroutine/function call
- Used to manage stack frame information during execution
- Works in conjunction with `SubroutineEnter` to track subroutine boundaries

### `VariableRead: Instruction`

Read a value from a variable and place its value, as expression, onto the stack.

#### Public API

- **Fields:**
  - `source_name: str` - Name of the variable to read
  - `source_is_local: bool` - Whether the variable is local (vs global)

- **Methods:**
  - `__init__(src: str, local: bool)` - Creates a variable read instruction
  - `__str__() -> str` - Returns `VariableRead [src=... (global/local)]`

#### Implementation details

- Reads from either local variables or global variables
- The `source_name` must be non-empty (asserted in constructor)
- The `source_is_local` flag determines whether to read from the current stack frame or global scope
- The read value is pushed onto the execution stack as an expression

### `VariableWrite: Instruction`

Write a new value to a variable. The value is being pulled from the top of the execution stack.

#### Public API

- **Fields:**
  - `destination_name: str` - Name of the variable to write to
  - `destination_is_local: bool` - Whether the variable is local (vs global)

- **Methods:**
  - `__init__(dst: str, local: bool)` - Creates a variable write instruction
  - `__str__() -> str` - Returns `VariableWrite [dst=... (global/local)]`

#### Implementation details

- Writes the top value from the execution stack to the specified variable
- The `destination_name` must be non-empty (asserted in constructor)
- The `destination_is_local` flag determines whether to write to the current stack frame or global scope
- The value is popped from the execution stack before writing

### `PrimitiveOps: Enum`

Enumeration of primitive arithmetic and logical operations.

#### Public API

- **Fields:**
  - `ADD`, `SUB`, `MUL`, `DIV`, `MOD` - Arithmetic operations (binary)
  - `AND`, `OR`, `XOR`, `SHR`, `SHL` - Bitwise operations (binary)
  - `EQ`, `NEQ`, `LESS`, `LEQ`, `GREATER`, `GEQ` - Comparison operations (binary)
  - `NEGATE`, `NOT` - Unary operations
  - `ABS` - Absolute value (unary)
  - `MAX`, `MIN` - Maximum/minimum of two values (binary)
  - `FLOOR` - Floor operation (unary)

- **Methods:**
  - `get_input_count() -> int` - Returns the number of input operands required

#### Implementation details

- Each enum value is a tuple: `(auto(), input_count)` where `input_count` is the number of operands
- Operations are performed on primitive values (integers, floats, etc.)
- The result is pushed back onto the stack

### `PrimitiveOp: Instruction`

Perform a N-nary operation on N values, pulled from the top of the stack, and place the result back on top.

#### Public API

- **Fields:**
  - `input_count: int` - Number of input operands (derived from operation)
  - `operation: PrimitiveOps` - The operation to perform

- **Methods:**
  - `__init__(op: PrimitiveOps)` - Creates a primitive operation instruction
  - `__str__() -> str` - Returns `PrimitiveOp [op=..., inputs=...]`

#### Implementation details

- Performs the specified `operation` on values popped from the stack
- The `input_count` is automatically set based on the operation
- Used for all arithmetic, logical, and comparison operations on primitive values

### `Assume: Instruction`

Make an assumption that the argument, pulled from the top of the stack, is `true`.

#### Public API

- **Methods:**
  - `__init__()` - Creates an assume instruction

#### Implementation details

- Used to assert conditions during symbolic execution
- The top value from the stack must be a boolean
- If the assumption is not satisfiable, the path is marked as invalid/not executable
- Critical for modeling conditional branches in program specifications

### `ContainerGetSize: Instruction`

Read the current size of a container. Container reference will be pulled from the top of the execution stack. The result will be placed back on top of the stack.

#### Public API

- **Methods:**
  - `__init__()` - Creates a container size read instruction

#### Implementation details

- Works with arrays, sets, maps; overwise returns `-1` for non-symbolic object instances
- The top value from the stack must be a valid container reference
- The container size is pushed back onto the stack

### `ArrayOps: Enum`

Enumeration of array operations.

#### Public API

- **Fields:**
  - `NEW` - Create a new array (1 input: size)
  - `SET_SIZE` - Set array size (2 inputs: ref, size)
  - `GET` - Get array element (2 inputs: ref, index)
  - `SET` - Set array element (3 inputs: ref, index, value)
  - `COPY` - Copy array segment (5 inputs: src, src_index, dst, dst_index, count)
  - `EQUALS_RANGE` - Compare array segments (5 inputs: a, a_index, b, b_index, count)

- **Methods:**
  - `get_input_count() -> int` - Returns the number of input operands required

#### Implementation details

- Arrays are 1-dimensional containers of primitive values
- Each operation has a specific number of input operands
- Used for all array-related operations

### `ArrayOperation: Instruction`

Perform an operation on a 1D array.

#### Public API

- **Fields:**
  - `item_type: PrimitiveTypeInfo` - Type of elements in the array
  - `operation: ArrayOps` - The array operation to perform

- **Methods:**
  - `__init__(op: ArrayOps, item_type: PrimitiveTypeInfo)` - Creates an array operation instruction
  - `__str__()` - Returns `ArrayOperation [op=..., type=...]`

#### Implementation details

- Performs the specified `operation` on array instance; used for creating, modifying, and querying array data
- The `item_type` specifies the *expected* type of elements in the array
- Array operations require valid container references and appropriate indices (although nothing stopping you from reading/writing elements outside of the `0..size-1` range; if this is an issue, consider adding extra checks/assertions)

### `SetOps: Enum`

Enumeration of set operations.

#### Public API

- **Fields:**
  - `NEW` - Create a new set (0 inputs)
  - `CONTAINS` - Check if set contains item (2 inputs: ref, item)
  - `ANY_ITEM` - Get any item from set (1 input: ref)
  - `ADD` - Add item to set (2 inputs: ref, item)
  - `REMOVE` - Remove item from set (2 inputs: ref, item)
  - `UNION` - Union of two sets (3 inputs: in_a, in_b, out_c)
  - `INTERSECTION` - Intersection of two sets (3 inputs: in_a, in_b, out_c)
  - `EQUALS` - Check if two sets are equal (2 inputs: in_a, in_b)

- **Methods:**
  - `get_input_count() -> int` - Returns the number of input operands required

#### Implementation details

- Sets are collections of unique primitive values
- Used for set-theoretic operations on collections of primitive values
- Operations like `UNION` and `INTERSECTION` require an output set instance that is **not** one of the input ones

### `SetOperation: Instruction`

Perform an operation on a "set" container object.

#### Public API

- **Fields:**
  - `item_type: PrimitiveTypeInfo` - Type of elements in the set
  - `operation: SetOps` - The set operation to perform

- **Methods:**
  - `__init__(op: SetOps, item_type: PrimitiveTypeInfo)` - Creates a set operation instruction
  - `__str__()` - Returns `SetOperation [op=..., type=...]`

#### Implementation details

- Performs the specified `operation` on set data; used for creating, modifying, and querying set data
- The `item_type` specifies the *expected* type of elements in the set
- Set operations require valid container references

### `MapOps: Enum`

Enumeration of map operations.

#### Public API

- **Fields:**
  - `NEW` - Create a new map (0 inputs)
  - `GET` - Get map value (2 inputs: ref, key)
  - `SET` - Set map value (3 inputs: ref, key, value)
  - `REMOVE` - Remove key from map (2 inputs: ref, key)
  - `HAS_KEY` - Check if map has key (2 inputs: ref, key)
  - `HAS_VALUE` - Check if map has value (2 inputs: ref, value)
  - `HAS_PAIR` - Check if map has key-value pair (3 inputs: ref, key, value)
  - `ANY_KEY` - Get any key from map (1 input: ref)
  - `ANY_VALUE` - Get any value from map (1 input: ref)
  - `UNION` - Union of two maps (3 inputs: in_a, in_b, out_c)
  - `INTERSECTION` - Intersection of two maps (3 inputs: in_a, in_b, out_c)
  - `EQUALS` - Check if two maps are equal (2 inputs: in_a, in_b)

- **Methods:**
  - `get_input_count() -> int` - Returns the number of input operands required

#### Implementation details

- Maps are key-value pairs where both keys and values are primitive types
- Operations like `UNION` and `INTERSECTION` require an output map instance that is different from inputs
- Used for associative array operations on primitive key-value pairs

### `MapOperation: Instruction`

Perform an operation on a "map" container object.

#### Public API

- **Fields:**
  - `kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]` - Type of keys and values
  - `operation: MapOps` - The map operation to perform

- **Methods:**
  - `__init__(op: MapOps, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo])` - Creates a map operation instruction
  - `__str__()` - Returns `MapOperation [op=..., type=...:...]`

#### Implementation details

- Performs the specified `operation` on map data; used for creating, modifying, and querying map data
- Both key and value types must be primitive (asserted in constructor)
- Map operations require valid container references

### `TransformOps: Enum`

Enumeration of transform operations.

#### Public API

- **Fields:**
  - `NEW` - Create a new transform (0 inputs)
  - `GET` - Get transform value (2 inputs: ref, key)
  - `SET` - Set transform value (3 inputs: ref, key, value)

- **Methods:**
  - `get_input_count() -> int` - Returns the number of input operands required

#### Implementation details

- Transforms are like maps but without a fixed size and behave similar to symbolic functions, although updates are allowed
- Used for representing transformations or mappings where the domain is not known in advance
- Suitable for dynamic single-argument transformations

### `TransformOperation: Instruction`

Perform an operation on a "transform" container-like object.

#### Public API

- **Fields:**
  - `kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]` - Type of keys and values
  - `operation: TransformOps` - The transform operation to perform

- **Methods:**
  - `__init__(op: TransformOps, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo])` - Creates a transform operation instruction
  - `__str__()` - Returns `TransformOperation [op=..., type=...:...]`

#### Implementation details

- Performs the specified `operation` on transform object
- Both key and value types must be primitive (asserted in constructor)
- Transform operations require valid container references

### `NewInstance: Instruction`

Create a new object of a given class. Reference to the newly created instance will be placed on top of the execution stack.

#### Public API

- **Fields:**
  - `structure_name: str` - Name of the structure/class to instantiate

- **Methods:**
  - `__init__(structure_name: str)` - Creates a new instance instruction
  - `__str__() -> str` - Returns `NewInstance [type=...]`

#### Implementation details

- Creates a new object instance with a unique reference based on `SymbolicStateMachine`'s internal counter (integer pointer)
- The `structure_name` must be non-empty (asserted in constructor)
- The reference is pushed onto the execution stack
- Performs only "allocation" and "default initialization" (suitable for structs but requires constructor invocation for complex objects)

### `FreeInstance: Instruction`

Mark an instance as "freed". An object cannot be "freed" more than once. Reference to the instance will be pulled from the top of the execution stack.

#### Public API

- **Methods:**
  - `__init__()` - Creates a free instance instruction

#### Implementation details

- Marks an object as freed (sets type information to that of `NULL`)
- The top value from the stack must be a valid object reference
- Objects cannot be freed more than once (enforced by the execution engine; adjust specs accordingly if needs to be caught)
- Can be used for simulating manual memory management and object lifecycle control

### `Copy: Instruction`

Makes N copies of a value from the X'th position of the execution stack (starting from the top) putting them back on top.

#### Public API

- **Fields:**
  - `number_of_copies: int` - Number of copies to make
  - `stack_position: int` - Position of the value to copy from (0 = top)

- **Methods:**
  - `__init__(*, count: int = 1, index: int = 0)` - Creates a copy instruction
  - `__str__() -> str` - Returns `Copy [count=..., pos=...]`

#### Implementation details

- The `number_of_copies` must be greater than `0`
- The `stack_position` specifies which stack element to copy (0 = top)
- Used for duplicating values on the stack (during handling of virtual calls, constructors, destructors)

### `FieldRead: Instruction`

Read a value from a field of an object's instance given a reference on the top of the stack. Place the acquired value, as expression, back onto the stack.

#### Public API

- **Fields:**
  - `source_field_name: str` - Name of the field to read
  - `source_structure_name: str` - Name of the structure/class containing the field

- **Methods:**
  - `__init__(struct: str, field: str)` - Creates a field read instruction
  - `__str__() -> str` - Returns `FieldRead [src=<struct>.<field>]`

#### Implementation details

- The object reference must point to a valid instance
- The `source_structure_name` and `source_field_name` must be non-empty
- It is technically possible to *read* from any field (with respect to primitive data types) from any type of object **unless** source instance is strictly `NULL`; please adjust your specifications accordingly to avoid undesired effects

### `FieldWrite: Instruction`

Write a new value to an object's instance field given a reference. The value and a reference are being pulled from the top of the execution stack.

#### Public API

- **Fields:**
  - `destination_field_name: str` - Name of the field to write to
  - `destination_structure_name: str` - Name of the structure/class containing the field

- **Methods:**
  - `__init__(struct: str, field: str)` - Creates a field write instruction
  - `__str__() -> str` - Returns `FieldWrite [dst=<struct>.<name>]`

#### Implementation details

- The top two values from the stack are popped: object reference and the new value
- The `destination_structure_name` and `destination_field_name` must be non-empty
- It is technically possible to *write* a value into any field (with respect to primitive data types) of any type of object **unless** destination instance is strictly `NULL`; please adjust your specifications accordingly to avoid undesired effects

### `InstanceOf: Instruction`

Checks if a given reference to an object is an instance of a specified class (or a subclass). The reference is pulled from the top of the stack. The result is placed back on top.

#### Public API

- **Fields:**
  - `exact_match: bool` - Whether to require exact type match (vs subclass)
  - `expected_structure_name: str` - Name of the structure/class to check against

- **Methods:**
  - `__init__(struct: str, *, exact: bool = False)` - Creates an instance-of instruction
  - `__str__() -> str` - Returns `InstanceOf [struct=..., exact=...]`

#### Implementation details

- The top value from the stack must be a reference
- The `expected_structure_name` must be non-empty
- The result expression is pushed onto the execution stack

### `SimpleDiff: Instruction`

Compares two values and returns `0` if they are equal and `1` otherwise. The values to compare are pulled from the top of the execution stack. The result is placed back on top.

#### Public API

- **Fields:**
  - `result_type: PrimitiveTypeInfo` - Type of the result value

- **Methods:**
  - `__init__(type: PrimitiveTypeInfo)` - Creates a simple diff instruction
  - `__str__() -> str` - Returns `SimpleDiff [type=...]`

#### Implementation details

- The top two values from the stack are popped and compared
- The `result_type` specifies the type of the return value
- Used for numerical equality comparisons in specifications

### `DistinctValues: Instruction`

Compares N values and returns a boolean value indicating whether all values are distinct. The values to compare are pulled from the top of the execution stack. The result is placed back on top.

#### Public API

- **Fields:**
  - `value_count: int` - Number of values to compare

- **Methods:**
  - `__init__(value_count: int)` - Creates a distinct values instruction
  - `__str__() -> str` - Returns `DistinctValues [count=...]`

#### Implementation details

- The `value_count` **must** be at least `1`
- The top `value_count` values from the stack are popped and compared
- Returns `true` if all values are distinct, `false` otherwise (put back on top of the execution stack)

### `FaultStatusRead: Instruction`

Read the current global "safeguard fault" machine status. The result (boolean) is placed on top of the execution stack.

#### Public API

- **Methods:**
  - `__init__()` - Creates a fault status read instruction

#### Implementation details

- Reads the global fault flag variable
- Useful for checking if a fault has occurred during execution (when `MachineConfig.fault_mode` is set to `STORE`)
- Part of the fault handling mechanism in the SVM

### `FaultStatusClear: Instruction`

Reset the current global "safeguard fault" machine status to "false".

#### Public API

- **Methods:**
  - `__init__()` - Creates a fault status clear instruction

#### Implementation details

- Resets the global fault flag variable to `false`
- Useful for clearing fault status after handling (little to no use outside `MachineConfig.fault_mode=STORE`)
- Part of the fault handling mechanism in the SVM

### `ExceptionRead: Instruction`

Read last thrown exception object reference. If no exception is currently active, this instruction will push a "null" reference onto the stack.

#### Public API

- **Methods:**
  - `__init__()` - Creates an exception read instruction

#### Implementation details

- Reads the global exception variable
- Returns the exception reference or `NULL`/`0` if no exception is active
- Part of the exception management mechanism in the SVM

### `ExceptionWrite: Instruction`

Set last thrown exception object reference to a given reference. The new reference is pulled from the top of the execution stack.

#### Public API

- **Methods:**
  - `__init__()` - Creates an exception write instruction

#### Implementation details

- Pops the top value from the stack and sets it as the exception reference
- Part of the exception management mechanism in the SVM (being used to throw exceptions)

### `StackBoundary: object`

Marker class for stack boundaries.

#### Public API

- **Fields.**
  - `uid: int` - Unique identifier for this boundary object

- **Methods:**
  - `__init__(self, uid: int | None = None)` - Creates a new stack boundary object with a specified ID (otherwise set to `id(self)`)
  - `__eq__(value: Any) -> bool` - Equality check based on type and `uid`
  - `__ne__(value: Any) -> bool` - Equality check based on type and `uid`
  - `__str__() -> str` - Returns a unique string representation with object ID (eg., `<stack-boundary#000002bbefac3b80>`)

#### Implementation details

Instances of this type are used with `ClearStackToBoundary` and `PushStackBoundary` instructions to mark boundaries in the execution stack as part of exception propagation and handling mechanism (see `micro_svm.exploration`).

### `ClearStackToBoundary: Instruction`

Clear the execution stack up to the specified stack boundary.

#### Public API

- **Fields:**
  - `boundary: StackBoundary | None` - The boundary to clear to

- **Methods:**
  - `__init__(boundary: StackBoundary | None)` - Creates a stack clear instruction

#### Implementation details

- Clears the execution stack up to (but not including) the specified boundary
- Used for handling (cross-procedural) stack cleanup during exception handling

### `PushStackBoundary: Instruction`

Push a new boundary object onto the execution stack.

#### Public API

- **Fields:**
  - `boundary: StackBoundary` - The boundary object to push

- **Methods:**
  - `__init__(boundary: StackBoundary)` - Creates a stack boundary push instruction

#### Implementation details

- Pushes a `StackBoundary` object onto the execution stack
- The `boundary` parameter must be a valid `StackBoundary` instance
- Used to mark boundaries in the execution stack for cleanup
- Works in conjunction with `ClearStackToBoundary`

### `StringOps: Enum`

Enumeration of string operations.

#### Public API

- **Fields:**
  - `LENGTH` - Get string length (1 input: str)
  - `CONCAT` - Concatenate strings (2 inputs: strA, strB)
  - `CONTAINS` - Check if string contains substring (2 inputs: str, sub)
  - `INDEX_OF` - Find substring index (3 inputs: str, sub, offset)
  - `LAST_INDEX_OF` - Find last substring index (2 inputs: str, sub)
  - `STARTS_WITH` - Check if string starts with prefix (2 inputs: str, prefix)
  - `ENDS_WITH` - Check if string ends with suffix (2 inputs: str, suffix)
  - `COPY` - Copy string segment (3 inputs: str, offset, count)
  - `REPLACE_ONCE` - Replace first occurrence (3 inputs: str, old, new)
  - `INT_TO_STR` - Convert integer to string (1 input: value)
  - `STR_TO_INT` - Convert string to integer (1 input: value)
  - `ORD` - Get character code (1 input: value)

- **Methods:**
  - `get_input_count() -> int` - Returns the number of input operands required

#### Implementation details

- Each operation has a specific number of expected input operands
- Used for all string-related operations in the SVM

### `StringOperation: Instruction`

Perform an operation with strings.

#### Public API

- **Fields:**
  - `operation: StringOps` - The string operation to perform

- **Methods:**
  - `__init__(op: StringOps)` - Creates a string operation instruction
  - `__str__()` - Returns `StringOperation [op=...]`

#### Implementation details

- Performs the specified `operation` on string data; used for creating, modifying, and querying string data
- String operations require valid string values

### `ContainerKind: Enum`

Enumeration of container types.

#### Public API

- **Fields:**
  - `ARRAY` - Array container (1 item type)
  - `SET` - Set container (1 item type)
  - `MAP` - Map container (2 item types: key and value)
  - `TRANSFORM` - Transform container (2 item types: key and value)

- **Methods:**
  - `get_input_count() -> int` - Returns the number of item types required

#### Implementation details

- Used to specify the type of container being checked or operated on
- *Maps* and *Transforms* require **2** item types (key and value), while *Arrays* and *Sets* only **1**

### `ContainerTypeCheck: Instruction`

Checks if the provided reference is a container object of a specific type.

#### Public API

- **Fields:**
  - `container_kind: ContainerKind` - The type of container to check
  - `item_types: list[PrimitiveTypeInfo]` - List of item types for the container

- **Methods:**
  - `__init__(kind: ContainerKind, items: list[PrimitiveTypeInfo])` - Creates a container type check instruction
  - `__str__()` - Returns `ContainerTypeCheck [kind=<container_kind>, items=<item_types>]`

#### Implementation details

- Validates that the reference is a container of the specified kind
- The `item_types` list must match the expected number of types for the container kind
- Can be useful for ensuring type safety when operating on containers

### `InstructionResolver: object`

Visitor pattern implementation for dispatching instructions to handlers.

#### Public API

- **Fields:**
  - `prefix: str` - Prefix for handler method names (default: `visit_instruction_`)
  - `visitor: object` - The visitor object with handler methods

- **Methods:**
  - `__init__(visitor: object, *, prefix: str = 'visit_instruction_')` - Creates an instruction resolver
  - `visit(ins: Instruction) -> None` - Dispatches an instruction to the appropriate handler

#### Implementation details

- Uses reflection to find handler methods on the visitor object
- Handler methods must be named `<prefix><ClassName>` where `<ClassName>` is the instruction class name (eg., `visit_instruction_Noop`)
- If no handler is found, raises `AssertionError`
- Critical for the instruction execution mechanism in the SVM

## Module-level functions

None.

---

*AI usage disclosure: this document was generated by a large language model, all text has been validated and edited by a human developer.*
