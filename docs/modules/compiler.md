# micro_svm.compiler

## Overview

### Summary

`CompilerContext` provides a high-level API for constructing executable specifications through a fluent interface that leverages Python operator overloading and builder patterns. It orchestrates the creation of `CompiledSubroutine` objects by managing basic blocks, local variables, and instruction sequences. The module supports primitive operations, container manipulations (arrays, sets, maps, transforms), field access, exception handling, and both static and virtual method calls. `Readable` objects encapsulate instruction sequences and enable arithmetic and comparison operations through dunder methods, while `VariableHandle` and `JoinedHandle` manage variable lifecycle and access patterns.

### Purpose

`CompilerContext` serves as the primary interface for programmatic specification assembly in the Micro-SVM project. It abstracts the low-level instruction generation process, allowing developers to write specifications using "natural" Python constructs. The context maintains compilation state including the current basic block, local variables, loop identifiers, and incomplete control flow graph builders. It provides methods for all supported operations including primitive arithmetic, container operations, object field access, exception handling, and method invocation. The design follows a single-entry, single-exit subroutine model for simplicity, with special handling for error paths via `error()`.

### Role in the Project

The compiler module is central to the Project's specification system, enabling the creation of executable program specifications that can be explored and validated. It works in conjunction with `GlobalContext` for function and structure metadata, `micro_svm.cfg` for control flow graph construction, and `micro_svm.instructions` for low-level instruction definitions. Specifications created via `CompilerContext` are used by `PathEnumerator` for path exploration, `SymbolicStateMachine` for symbolic execution. The module's output is serialized via `micro_svm.serialization` for storage and loading.

### Contracts

- `CompilerContext` expects `FunctionInfo` objects from `GlobalContext` to provide parameter metadata and result type information.
- All `VariableHandle` objects must be created via `CompilerContext` methods (`make_local_variable()`, `get_global_variable()`, `get_parameter()`, `get_function_result()`).
- `JoinedHandle` objects combine a `Readable` (read handle) with a `VariableHandle` (write handle) and must be used consistently for variable operations.
- `call()` method requires proper handling of return types; when `discard_result=True` is set, the return value is explicitly popped from the stack.
- Loop constructs (`begin_loop()`, `loop_break()`, `loop_continue()`) require proper nesting and must be used within the context of a loop ID stack managed by `CompilerContext`.
- Exception handling via `begin_try()` requires at least one catch handler or a finally handler to be registered.
- `error()` marks the current path as failed and sets `_ignore_followup_instructions` to `True`, preventing further instruction generation on that path.

## Classes

### `CompilerContext: object`

`CompilerContext` manages the compilation state and provides methods for generating instructions. It maintains the current basic block, local variables, loop identifiers, and incomplete control flow graph builders. The context is initialized with an optional `FunctionInfo` object representing the function being compiled.

#### Public API

- **Fields:**
  - `current_function: FunctionInfo | None` - The function currently being compiled, or `None` for top-level specifications

- **Methods:**
  - `abs(value: Readable) -> Readable` - Computes absolute value
  - `array_copy(item_type: PrimitiveTypeInfo | None, src: Readable, src_index: Readable, dst: Readable, dst_index: Readable, count: Readable) -> None` - Copies elements between arrays
  - `array_equals_range(item_type: PrimitiveTypeInfo, a: Readable, a_index: Readable, b: Readable, b_index: Readable, count: Readable) -> Readable` - Checks if two array ranges are equal
  - `array_get(item_type: PrimitiveTypeInfo, array_ref: Readable, index: Readable) -> Readable` - Gets an array element
  - `array_new(item_type: PrimitiveTypeInfo, size: Readable) -> Readable` - Creates a new array
  - `array_set_size(item_type: PrimitiveTypeInfo, array_ref: Readable, size: Readable) -> None` - Sets the size of an array
  - `array_set(item_type: PrimitiveTypeInfo, array_ref: Readable, index: Readable, value: Readable) -> None` - Sets an array element
  - `assume(expression: Readable) -> None` - Adds an assumption/constraint to the current path
  - `begin_if(condition: BranchCallbackWithResult) -> IfBuilder` - Creates an if-then-else block
  - `begin_loop(condition: BranchCallbackWithResult) -> LoopBuilder` - Creates a while loop
  - `begin_switch(value_type: PrimitiveTypeInfo, value: BranchCallbackWithResult) -> SwitchBuilder` - Creates a switch statement
  - `begin_try(body: BranchCallback) -> TryBuilder` - Creates a try-catch-finally block
  - `build() -> CompiledSubroutine` - Compiles the current subroutine, adding entry/exit blocks and initializing parameters and return value
  - `call(function_or_method: str | tuple[str, str], args: list[Readable], return_type: PrimitiveTypeInfo | None, *, discard_result: bool = False, virtual: bool = True) -> Readable | None` - Calls a static or virtual function/method
  - `clear_fault_status() -> None` - Clears the fault status flag
  - `concat_strings(str_a: Readable, str_b: Readable) -> Readable` - Concatenates two strings
  - `const(value: object, type: PrimitiveTypeInfo = integer) -> Readable` - Creates a `Readable` containing a constant value
  - `container_size(container_ref: Readable) -> Readable` - Returns the size of a container
  - `distinct_values(values: list[Readable]) -> Readable` - Checks if the provided values are distinct or not
  - `end_of_program() -> None` - Marks the end of the program
  - `error(metadata: str | None = None) -> None` - Marks the current path as failed
  - `field_read(instance_ref: Readable, structure_name: str, field_name: str) -> Readable` - Reads a field value from an object
  - `field_write(instance_ref: Readable, structure_name: str, field_name: str, value: Readable) -> None` - Writes a new value to a field of an object
  - `floor(value: Readable) -> Readable` - Computes floor value
  - `free_instance(ref: Readable, destructor: str | tuple[str, str] | None = None) -> None` - Frees an instance (with optional destructor call)
  - `get_fault_status() -> Readable` - Reads the fault status flag
  - `get_function_result() -> JoinedHandle` - Retrieves the function result variable as a `JoinedHandle`
  - `get_global_variable(name: str) -> JoinedHandle` - Retrieves a global variable as a `JoinedHandle`
  - `get_parameter(name: str) -> JoinedHandle` - Retrieves a function parameter as a `JoinedHandle`
  - `get_string_length(s: Readable) -> Readable` - Gets the length of a string
  - `instance_of(ref: Readable, structure_name: str, *, exact_match: bool = False) -> Readable` - Checks if an object is an instance of a specific structure/class type
  - `integer_to_string(value: Readable) -> Readable` - Converts an integer to a string
  - `is_array(ref: Readable, item_type: PrimitiveTypeInfo) -> Readable` - Checks if a reference points to an array
  - `is_map(ref: Readable, key_type: PrimitiveTypeInfo, value_type: PrimitiveTypeInfo) -> Readable` - Checks if a reference points to a map
  - `is_set(ref: Readable, item_type: PrimitiveTypeInfo) -> Readable` - Checks if a reference points to a set
  - `is_transform(ref: Readable, key_type: PrimitiveTypeInfo, value_type: PrimitiveTypeInfo) -> Readable` - Checks if a reference points to a transform
  - `loop_break() -> None` - Breaks out of the current loop
  - `loop_continue() -> None` - Continues to the next iteration of the current loop
  - `make_local_variable(type: PrimitiveTypeInfo, tags: set[str] | None = None) -> JoinedHandle` - Creates a new local variable and returns a `JoinedHandle` for read/write access
  - `map_any_key(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], map_ref: Readable) -> Readable` - Gets an arbitrary key from a map
  - `map_any_value(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], map_ref: Readable) -> Readable` - Gets an arbitrary value from a map
  - `map_equals(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], a: Readable, b: Readable) -> Readable` - Checks if two maps are equal
  - `map_get(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], map_ref: Readable, key: Readable) -> Readable` - Gets a map value
  - `map_has_key(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], map_ref: Readable, key: Readable) -> Readable` - Checks if a map has a key
  - `map_has_pair(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], map_ref: Readable, key: Readable, value: Readable) -> Readable` - Checks if a map has a key-value pair
  - `map_has_value(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], map_ref: Readable, value: Readable) -> Readable` - Checks if a map has a value
  - `map_intersection(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], in_a: Readable, in_b: Readable, out: Readable) -> None` - Computes map intersection
  - `map_new(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> Readable` - Creates a new map
  - `map_remove(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], map_ref: Readable, key: Readable) -> None` - Removes a map entry
  - `map_set(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], map_ref: Readable, key: Readable, value: Readable) -> None` - Sets a map value
  - `map_union(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], in_a: Readable, in_b: Readable, out: Readable) -> None` - Computes map union
  - `max(a: Readable, b: Readable) -> Readable` - Computes maximum value
  - `min(a: Readable, b: Readable) -> Readable` - Computes minimum value
  - `new_instance(structure_name: str, constructor: str | None = None, args: list[Readable] = None) -> Readable` - Creates a new instance of a structure
  - `noop(comment: str | None = None) -> None` - Adds a no-op instruction (for documentation/comments)
  - `set_add(item_type: PrimitiveTypeInfo, set_ref: Readable, item: Readable) -> None` - Adds an item to a set
  - `set_contains(item_type: PrimitiveTypeInfo, set_ref: Readable, item: Readable) -> Readable` - Checks if a set contains an item
  - `set_equals(item_type: PrimitiveTypeInfo, a: Readable, b: Readable) -> Readable` - Checks if two sets are equal
  - `set_get_any(item_type: PrimitiveTypeInfo, set_ref: Readable) -> Readable` - Gets an arbitrary item from a set
  - `set_intersection(item_type: PrimitiveTypeInfo, in_a: Readable, in_b: Readable, out: Readable) -> None` - Computes set intersection
  - `set_new(item_type: PrimitiveTypeInfo) -> Readable` - Creates a new set
  - `set_remove(item_type: PrimitiveTypeInfo, set_ref: Readable, item: Readable) -> None` - Removes an item from a set
  - `set_union(item_type: PrimitiveTypeInfo, in_a: Readable, in_b: Readable, out: Readable) -> None` - Computes set union
  - `simple_diff(result_type: PrimitiveTypeInfo, condition_same: Readable) -> Readable` - Creates a simple difference operation
  - `string_contains(s: Readable, substr: Readable) -> Readable` - Checks if a string contains a substring
  - `string_copy(s: Readable, offset: Readable, count: Readable) -> Readable` - Copies a substring
  - `string_ends_with(s: Readable, suffix: Readable) -> Readable` - Checks if a string ends with a suffix
  - `string_index_of(s: Readable, sub: Readable, offset: Readable) -> Readable` - Finds the index of a substring
  - `string_last_index_of(s: Readable, sub: Readable) -> Readable` - Finds the last index of a substring
  - `string_ord(s: Readable) -> Readable` - Gets the ordinal value of a character
  - `string_replace(s: Readable, old: Readable, new: Readable) -> Readable` - Replaces a substring once
  - `string_starts_with(s: Readable, prefix: Readable) -> Readable` - Checks if a string starts with a prefix
  - `string_to_integer(value: Readable) -> Readable` - Converts a string to an integer
  - `symbolic(type: PrimitiveTypeInfo) -> Readable` - Creates a `Readable` containing a symbolic (unconstrained) value
  - `throw(value: Readable) -> None` - Throws an exception
  - `transform_get(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], transform_ref: Readable, key: Readable) -> Readable` - Gets a transform value
  - `transform_new(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> Readable` - Creates a new transform
  - `transform_set(kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo], transform_ref: Readable, key: Readable, value: Readable) -> None` - Sets a transform value
  - `write(var: VariableHandle, value: Readable) -> None` - Writes a `Readable` value to a variable

#### Implementation details

`CompilerContext` uses a builder pattern where `Readable` objects collect consecutive instructions. When an operation is performed (e.g., `array_get()`), the method returns a new `Readable` that chains the previous instructions with the new operation. This allows for fluent composition like `ctx.array_get(type, array, index)` where the result can be used directly in subsequent operations.

`VariableHandle`s are used for writes, while `Readable` objects are used for reads, both combined into `JoinedHandle`s. When writing to a variable, the `write()` method adds the value's instructions followed by a `VariableWrite` instruction.

Control flow constructs like `begin_if()`, `begin_loop()`, `begin_switch()`, and `begin_try()` use a deferred execution model. They create `IfBuilder`, `LoopBuilder`, `SwitchBuilder`, or `TryBuilder` objects that capture the current state and are later "explored" to generate the actual control flow graph. This allows for natural Python syntax while still building the appropriate CFG nodes.

Error handling is managed via the `_ignore_followup_instructions` flag. When `error()` is called, this flag is set to `True`, preventing further instruction generation on that path. This is important for handling unreachable code after error conditions.

Loop management uses a stack-based approach with `_loop_id_stack`. Loop identifiers are generated via `_next_loop_id()` and pushed when entering a loop (via `begin_loop()` for while loops) and popped when exiting. This allows `loop_break()` and `loop_continue()` to target the correct loop.

### `Readable: object`

`Readable` represents a sequence of instructions that can be executed. It is used throughout the compiler API to represent values that can be composed using Python operators. The class is marked with `@final` to prevent inheritance.

#### Public API

- **Fields:**
  - `instructions: tuple[Instruction]` - The sequence of instructions represented by this `Readable` object

- **Methods:**
  - `__add__(other: Readable) -> Readable` - Composition via addition
  - `__sub__(other: Readable) -> Readable` - Composition via subtraction
  - `__mul__(other: Readable) -> Readable` - Composition via multiplication
  - `__div__(other: Readable) -> Readable` - Composition via division
  - `__truediv__(other: Readable) -> Readable` - Alias for `__div__()`
  - `__mod__(other: Readable) -> Readable` - Composition via modulo
  - `__and__(other: Readable) -> Readable` - Composition via bitwise AND
  - `__or__(other: Readable) -> Readable` - Composition via bitwise OR
  - `__xor__(other: Readable) -> Readable` - Composition via bitwise XOR
  - `__rshift__(other: Readable) -> Readable` - Composition via right bit-shift
  - `__lshift__(other: Readable) -> Readable` - Composition via left bit-shift
  - `__eq__(other: Readable) -> Readable` - Composition via equality
  - `__ne__(other: Readable) -> Readable` - Composition via inequality
  - `__lt__(other: Readable) -> Readable` - Composition via less-than
  - `__le__(other: Readable) -> Readable` - Composition via less-than-or-equal
  - `__gt__(other: Readable) -> Readable` - Composition via greater-than
  - `__ge__(other: Readable) -> Readable` - Composition via greater-than-or-equal
  - `__pos__(self) -> Readable` - Returns the `self` unchanged (identity operation)
  - `__neg__(self) -> Readable` - Composition via negation
  - `__invert__(self) -> Readable` - Composition via bitwise NOT

#### Implementation details

`Readable` objects are immutable in the sense that they cannot be modified after creation. Operations like `__add__()` create new `Readable` objects by concatenating the instructions from both operands and adding a new `PrimitiveOp` instruction. This design allows for natural, readable code while maintaining the ability to track instruction sequences.

### `VariableHandle: object`

`VariableHandle` represents a variable with a name, type, and local flag. It is used for writing to variables and is paired with a `Readable` for reading.

#### Public API

- **Fields:**
  - `name: str` - The name of the variable
  - `type: PrimitiveTypeInfo | None` - The type of the variable, or `None` if unknown
  - `is_local: bool` - Whether the variable is local to the current function

### `JoinedHandle: object`

`JoinedHandle` combines a `Readable` (read handle) with a `VariableHandle` (write handle), providing convenient access to both read and write operations for a variable.

#### Public API

- **Fields:**
  - `r: Readable` - The read handle for the variable
  - `w: VariableHandle` - The write handle for the variable

### `GraphJunctionBuilder: ABC`

`GraphJunctionBuilder` is an abstract base class for building control flow graph junctions. It is used by branching methods to defer the construction of control flow until the branching point is fully specified and to warn about incomplete/hanging builders.

#### Public API

- **Fields:** (none)

- **Methods:** (none)

### `CompilerContext.IfBuilder: GraphJunctionBuilder`

`IfBuilder` constructs an if-then-else control flow block. It is returned by `begin_if()` and provides methods to specify the then and else branches.

#### Public API

- **Methods:**
  - `then(action: BranchCallback) -> IfBuilder` - Specifies the then branch
  - `otherwise(action: BranchCallback) -> IfBuilder` - Specifies the else branch
  - `end_if() -> None` - Finalizes the if block and connects it to the control flow graph

### `CompilerContext.LoopBuilder: GraphJunctionBuilder`

`LoopBuilder` constructs a while loop control flow block. It is returned by `begin_loop()` and provides a method to specify the loop body.

#### Public API

- **Methods:**
  - `body(action: BranchCallback) -> LoopBuilder` - Specifies the loop body
  - `end_loop() -> None` - Finalizes the loop and connects it to the control flow graph

### `CompilerContext.SwitchBuilder: GraphJunctionBuilder`

`SwitchBuilder` constructs a switch statement control flow block. It is returned by `begin_switch()` and provides methods to specify case handlers and a default handler.

#### Public API

- **Methods:**
  - `when(value: ValueType, handler: BranchCallback) -> SwitchBuilder` - Specifies a case handler for a particular value
  - `otherwise(wildcard_handler: BranchCallback) -> SwitchBuilder` - Specifies a default handler for unmatched values
  - `end_switch() -> None` - Finalizes the switch and connects it to the control flow graph

### `CompilerContext.TryBuilder: GraphJunctionBuilder`

`TryBuilder` constructs a try-catch-finally control flow block. It is returned by `begin_try()` and provides methods to specify catch handlers and a finally handler.

#### Public API

- **Methods:**
  - `catch(error_structure_type: str, handler: TypedExceptionHandlerCallback) -> TryBuilder` - Specifies a catch handler for a specific error structure type
  - `final(handler: BranchCallback) -> TryBuilder` - Specifies a finally handler
  - `end_try() -> None` - Finalizes the try block and connects it to the control flow graph

## Module-level functions

None.

---

*AI usage disclosure: this document was generated by a large language model, all text has been validated and edited by a human developer.*
