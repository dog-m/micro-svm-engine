# micro_svm.global_context

## Overview

### Summary

`GlobalContext` serves as the central registry and assembly point for program/library specifications in the Micro-SVM project. It maintains comprehensive metadata about global variables, functions, structures, and symbols, enabling programmatic specification creation through the `CompilerContext` API. The module provides methods for registering and retrieving program components, managing function implementations, and visualizing compiled specifications.

### Purpose

`GlobalContext` provides the foundational data structure for representing executable program specifications. It acts as a container for all program-level entities including global variables, functions (both static and methods), and user-defined structures. The class supports dynamic registration of program components with optional inline implementation compilation, enabling the creation of self-contained specifications that can be serialized, loaded, and executed by the symbolic virtual machine. The module also includes a visualization utility for inspecting compiled specifications.

### Role in the Project

`GlobalContext` is the central hub for program specification assembly in the Micro-SVM project. It serves as the primary interface between user-defined specifications and the symbolic execution engine. All program-level entities are registered with a `GlobalContext` instance, which then provides access to these entities during path exploration and symbolic execution. The module works in conjunction with `CompilerContext` to enable declarative specification writing, with `cfg.py` for control-flow graph construction, and `serialization.py` for persistent storage and loading of specifications.

### Contracts

- **Symbol Resolution**: When retrieving symbols via `get_symbol()`, checking `global_variables` is prioritized over `other_symbols` collection.
- **Function Registration**: When registering functions with a `structure` parameter, the function name is automatically transformed using `structure_member_to_signature()` to create proper method signatures. Static functions are registered with `structure=None` and `static=True`. Each function in a user specification is assumed to have a **unique full name**.
- **Implementation Compilation**: When `implementation` is provided to `register_function()`, it is compiled immediately using `CompilerContext` and the compiled result is stored in `func.implementation`. Any compilation errors are raised as `SyntaxError`.
- **Structure Registration**: When registering structures via `register_structure()`, parent structures are stored in `parents` and fields are added to `fields` respectively. The structure is stored in `GlobalContext.structures`.
- **Function Symbols**: When `register_function_symbols()` is called, it registers function parameters, local variables, and result variables as symbols in `other_symbols` with fully qualified names (e.g., `function_name#parameter_name`).

## Classes

### `GlobalContext`

`GlobalContext` serves as the central registry for program specifications. It maintains collections of all program/library-level entities and provides methods for registering and retrieving these entities.

#### Public API

- **Fields:**
  - `functions: dict[str, FunctionInfo]` - Dictionary mapping function signatures to their metadata including parameters, result type, implementation, and tags.
  - `global_variables: dict[str, VariableInfo]` - Dictionary mapping global variable names to their metadata including type, initializer value, and tags.
  - `other_symbols: dict[str, VariableInfo]` - Dictionary mapping symbol names (including local variables, parameters, and function results) to their metadata.
  - `structures: dict[str, StructureTypeInfo]` - Dictionary mapping structure names to their type information including parent structures and field definitions.

- **Methods:**
  - `get_field_type(struct: str, field: str) -> TypeInfo` - Returns the type information for a specific field in a structure.
  - `get_method_info(structure: str, method: str) -> FunctionInfo` - Returns the function information for a method of a structure.
  - `get_symbol(name: str) -> VariableInfo` - Retrieves a symbol by name, checking global variables first, then other symbols.
  - `register_global_variable(name: str, type: TypeInfo, *, initializer: InitializerValueType = None, tags: set[str] | None = None) -> None` - Registers a global variable with optional initializer and tags.
  - `register_function(name: str, parameters: list[tuple[str, TypeInfo]], result: TypeInfo | None, implementation: Callable[[CompilerContext], None] | None = None, *, tags: set[str] | None = None, structure: str | None = None, static: bool = False) -> None` - Registers a function with optional implementation, handling method signature transformation and static function registration.
  - `register_function_symbols(func: FunctionInfo) -> None` - Registers function parameters, local variables, and result as symbols.
  - `register_structure(name: str, parents: list[str] | None = None, fields: list[FieldInfo] | None = None) -> None` - Registers a structure with parent classes and field definitions.
  - `register_symbol(var: VariableInfo) -> None` - Registers a symbol in the `other_symbols` dictionary.

#### Implementation details

`GlobalContext` implements a centralized registry pattern where all program-level entities are stored in separate dictionaries for efficient lookup. The `get_symbol()` method implements a two-tier lookup strategy, prioritizing global variables over other symbols, which allows for proper scoping resolution during symbolic execution.

The `register_function()` method handles both static functions and methods. When a `structure` parameter is provided, the function name is transformed using `structure_member_to_signature()` to create proper method signatures (e.g., `ClassName.methodName`). The method also manages static method registration by storing the transformed name in the appropriate structure's static methods dictionary (thus requiring registering structures *before* functions).

Function implementation compilation is performed inline during registration. When an `implementation` callable is provided, it is wrapped in a `CompilerContext` instance, executed, and the compiled result is stored. This enables immediate validation of function specifications and allows the function to be executed directly during path exploration without recompilation. The absence of an `implementation` implies an *abstract* method and by extension the binding structure itself.

The `register_function_symbols()` method ensures proper symbol scoping by registering function parameters, local variables, and result variables with fully qualified names that include the function name prefix (e.g., `function_name#parameter_name`). This scoping mechanism is essential for the symbolic execution engine to correctly resolve variables based on the current stack frame.

## Module-level functions

- `show_compiled_specs(spec: GlobalContext) -> None` - Visualizes the compiled specification by printing global variables, functions, and structures in a human-readable format. This utility is primarily used for debugging and inspection during specification development.

---

*AI usage disclosure: this document was generated by a large language model, all text has been validated and edited by a human developer.*
