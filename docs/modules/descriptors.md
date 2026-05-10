# micro_svm.descriptors

## Overview

### Summary

`VariableInfo`, `CompiledSubroutine`, and `FunctionInfo` classes provide core metadata descriptors for variables, subroutines, and functions within the symbolic virtual machine's program specifications. These descriptors define type information, initialization values, tags, parameter signatures, and compiled implementations, serving as the foundational data structures for program analysis and symbolic execution. `VariableInfo` tracks variable metadata including name, type, initializer, and tags; `CompiledSubroutine` encapsulates a function's entry point and local variable declarations; `FunctionInfo` describes function/method signatures with parameters, result types, static status, and implementation references. These descriptors are essential for managing the global context, enabling type hierarchy resolution, and supporting the symbolic execution engine's path enumeration capability.

### Purpose

The `descriptors` module provides the structural foundation for representing program entities in the symbolic virtual machine. It defines the metadata schema for variables, functions, and subroutines that constitute executable specifications. These descriptors are used throughout the system to track type information, manage variable scopes, resolve function calls, and enable the symbolic execution engine to understand program structure. The descriptors support both static analysis (type checking, hierarchy resolution) and dynamic execution (parameter passing, variable tracking, implementation lookup). By separating metadata from implementation details, the system enables flexible program specification and efficient path exploration.

### Role in the Project

The descriptors module serves as the central metadata repository for program specifications in the symbolic virtual machine. It is used by `GlobalContext` to maintain the complete program state including types, global variables, functions, and their implementations. These descriptors are essential for:

- **Type hierarchy resolution**: `FunctionInfo` and `VariableInfo` provide the type information needed by `TypeHierarchyResolver` to resolve virtual calls and field access across class hierarchies (see `micro_svm.type_hierarchy`).
- **Symbolic execution**: `CompiledSubroutine` provides the entry point and local variable declarations needed for path enumeration in `micro_svm.exploration` module.
- **Serialization**: The descriptor structures map directly to the JSON specification format used for saving and loading program specifications.

### Contracts

The descriptors module makes several assumptions about the objects and values it receives from other modules:

- **VariableInfo**: Expects `name` to be a non-empty string, `type` to be a valid `TypeInfo` instance, and `initializer` to be one of the supported types (bool, int, float, str, None, dict, list of tuples, or list of values). Tags should be a set of strings or None.
- **FunctionInfo**: Expects `original_name` to be a non-empty string, `parameters` to be a dictionary mapping parameter names to `TypeInfo` instances, and `tags` to be a set of strings. The `structure` field should be None for global functions or a valid structure name for methods. `result_type` can be None for void functions.
- **CompiledSubroutine**: Expects `entry_node` to be a valid CFG `Node` instance and `temp_variables` to be a list of `VariableInfo` instances representing local variables.
- **Hash/Equality**: `VariableInfo` uses only the `name` field for hashing and equality comparison.
- **Function signature**: `FunctionInfo.full_name` is constructed using `structure_member_to_signature()` for methods.

## Classes

### `VariableInfo: object`

`VariableInfo` represents metadata for a variable in the program specification. It encapsulates the essential information needed to track variables throughout symbolic execution, including their names, types, initial values, and optional tags for classification or filtering.

#### Public API

- **Fields:**
  - `initializer: InitializerValueType` - The initial value for the variable, supporting various types including primitives, dictionaries, lists, and tuples. Can be None for uninitialized variables.
  - `name: str` - The variable's identifier name, used for referencing the variable in instructions and expressions.
  - `tags: set[str]` - A collection of string tags for categorizing or annotating the variable (e.g., for filtering in analysis or other uses).
  - `type: TypeInfo` - The variable's type information, defining its data structure and behavior (e.g., primitive types, references, containers).

#### Implementation details

`VariableInfo` implements hash and equality based solely on the variable name, which is a deliberate design choice for simplicity but may cause issues if variables with the same name but different types or initializers are treated as equivalent. The `initializer` field supports multiple types to accommodate different initialization scenarios:

- primitive values (bool, int, float, str, None),
- dictionaries for objects/structures,
- lists for arrays/sets,
- and tuples for key-value pairs (maps and transforms).

This flexibility allows the system to represent various initialization patterns while maintaining a consistent interface.

### `CompiledSubroutine: object`

`CompiledSubroutine` represents a compiled subroutine implementation, containing the entry point into the subroutine's control flow graph and the declaration of local variables. This descriptor is used by the symbolic execution engine to understand the structure of function implementations during path enumeration.

#### Public API

- **Fields:**
  - `entry_node: Node` - The entry `Node` of the subroutine's control flow graph, marking the starting point for execution.
  - `local_variables: list[VariableInfo]` - A list of `VariableInfo` instances representing local variables declared within this subroutine, excluding parameters.

#### Implementation details

The `entry_node` field references a `Node` from the control flow graph, which contains the actual instruction sequence. The `local_variables` list provides the complete set of local variable declarations, which are essential for tracking variable lifetimes and managing stack frames during symbolic execution. The `CompiledSubroutine` descriptor is typically created by the `CompilerContext` during specification assembly and is used by the path enumerator to expand subroutine calls during exploration.

### `FunctionInfo: object`

`FunctionInfo` provides comprehensive metadata for functions and methods in the program specification. It describes the function's signature, parameters, return type, static status, and optionally its compiled implementation. This descriptor is central to function resolution, call handling, and program analysis.

#### Public API

- **Fields:**
  - `full_name: str` - The signature name for this function, combining structure name and method name with a dot separator for methods, or just the original name for global functions.
  - `implementation: CompiledSubroutine | None` - The implementation of this function (`None` for abstract methods).
  - `is_static: bool` - A flag indicating whether this is a static method or instance method.
  - `original_name: str` - The function's original name as declared in the specification.
  - `parameters: dict[str, TypeInfo]` - A (ordered) dictionary mapping parameter names to their type information.
  - `result_type: TypeInfo | None` - The return type of the function (`None` for void).
  - `structure: str | None` - The name of the structure/class this method belongs to (`None` for global functions).
  - `tags: set[str]` - A collection of string tags for categorizing or annotating the function.

- **Methods:**
  - `get_full_parameter_name (name: str): str` - Returns the fully qualified parameter name by combining the function's full name with the parameter name using a separator (e.g., `map_get#key`).

#### Implementation details

`FunctionInfo` uses a class-level constant `RESULT_NAME = "~result"` to represent the implicit result variable in the function's local scope (note that the result variable is also functions as a "parameter"). The `full_name` property is computed dynamically based on whether the function is a method or global function, using `structure_member_to_signature()` for methods. This naming convention is important for distinguishing between parameters of different functions and for tracking variable references during symbolic execution. The `parameters` dictionary provides a convenient interface for accessing parameter types by name, which is used during call argument resolution and type checking. The `is_static` flag is essential for determining how the function should be called and how the `this` parameter should be handled during execution (always expected being first when applicable).

## Module-level functions

- `structure_member_to_signature (structure_name: str, member_name: str): str` - Creates a fully qualified signature string for a structure member by concatenating the structure name and member name with a dot separator (e.g., `std.List.AddLast`). This function is used to generate fully qualified names for methods and to distinguish between methods with the same name in different structures.

---

*AI usage disclosure: this document was generated by a large language model, all text has been validated and edited by a human developer.*
