# micro_svm.execution

## Overview

### Summary

This module implements the Symbolic Virtual Machine (SVM), a core component for symbolic execution of program instructions. It processes sequences of instructions to validate paths, decode program states from symbolic models and detect defects through constraint solving with Z3. The module handles variable versioning, container operations (arrays, sets, maps, transforms), object instances, fault management, and exception handling, enabling precise state analysis.

### Purpose

The primary purpose of this module is to provide a symbolic execution engine that can validate program paths, producing concrete object states as a byproduct.

### Role in the Project

This module serves as the execution engine for the SVM, which is central to the project's path exploration, state decoding, and defect detection capabilities. It processes instructions generated during path enumeration, validates them against constraints, and provides the foundation for analyzing desired object states.

### Contracts

- Uses `GlobalContext` for *symbol* and *type* information

## Classes

### `SymbolicStateMachine: object`

The symbolic state machine is the core execution engine that processes sequences of symbolic instructions and accumulates Z3 constraints representing program paths. It implements SSA-based variable management, pool-based container allocation, and configurable fault handling to enable precise symbolic state analysis. The machine supports a comprehensive instruction set including primitive operations, array/set/map/transform manipulations, object instance creation, field access, string operations, and control points for path exploration.

#### Public API

- **Fields**:
  - `config: MachineConfig` - Configuration object for solver behavior and fault handling
  - `context: GlobalContext` - Global context providing symbol and type information
  - `debug_dump_expressions: bool` - Prints all stored expressions for debugging on the console
  - `debug_unknown: bool` - Enables debugging for "unknown" solver results
  - `debug_unsat: bool` - Enables debugging output for unsatisfiable paths
  - `is_running: bool` - Indicates whether the symbolic execution is still viable (True) or has become infeasible (False)
  - `statistics: SymbolicStateMachineStatistics` - Tracks statistics about created objects during execution

- **Methods**:
  - `advance_ref_counter(delta: int) -> None` - Increments the internal object instance counter by the given delta, effectively reserving N consecutive *symbolic* reference IDs for subsequent object allocations
  - `check() -> None` - Finalizes symbolic execution by running the Z3 solver to validate all accumulated constraints; sets `is_running` based on satisfiability
  - `execute(instructions: Iterable[Instruction], *, flush: bool = False) -> bool` - Executes a sequence of instructions and optionally clears the execution stack; returns feasibility status
  - `flush_execution_stack() -> None` - Clears the execution stack and resets the stack frame counter
  - `make_temp_variable(type: TypeInfo) -> VersionedVariable` - Creates a temporary variable with a unique name for intermediate computations
  - `play(instructions: Iterable[Instruction]) -> None` - Executes a sequence of instructions without resetting `is_running` flag
  - `pull(count: int = 1) -> object | list[object]` - Removes and returns one or more items from the top of the execution stack
  - `push(value: object) -> None` - Pushes a value onto the execution stack
  - `read(var: VersionedVariable) -> z3.ExprRef` - Resolves a versioned variable to its current Z3 expression
  - `set_current_container_size_limit(max_size: int) -> None` - Sets a global upper bound on container sizes for all objects
  - `show_expressions() -> None` - Prints all current constraint expressions to stdout
  - `show_stack() -> None` - Prints the current execution stack contents to stdout
  - `step(instruction: Instruction) -> bool` - Executes a single instruction and returns `True` if the machine is still running, `False` otherwise
  - `to_versioned(original_name: str, *, is_local: bool = False, stack_frame: int | None = None) -> VersionedVariable` - Converts a variable name to a versioned variable, applying stack frame prefixing for locals
  - `visit_instruction_*` - A family of methods for handling various instructions. There are sub-families of handlers that are specific to grouped instructions (eg., `visit_set_op_*`, `visit_string_op_*`) each one dedicated for handling a concrete variation.
  - `write(var: VersionedVariable, value: z3.ExprRef) -> None` - Registers an "update" Z3 expression over a versioned variable, incrementing its version (SSA semantics)

#### Implementation details

- Uses SSA (Static Single Assignment) for variable management, where each write operation increments the variable version
- Maintains a constraint store (`_expressions` list) that accumulates Z3 formulas throughout execution
- Uses `UF_ASLIA` theory solver for uninterpreted functions with arrays, integers, and bit-vectors
- Enables solver expression tracking via `smt.core.minimize` for unsat core extraction when debugging is enabled
- Uses a type ID system based on GUID sequences to track object types at runtime
- Implements pool-based allocation for collections, where each container instance is referenced by an integer ID and stored in type-specific pools
- Container operations (arrays, sets, maps, transforms) are modeled using Z3 arrays with universal and existential quantifiers for element membership checks ("rule-of-thumb" operation complexity can be expressed via `array <= transform < set < map`)
- Fault handling is configurable via `FaultMode` (IGNORE, AVOID, STORE), determining whether fault conditions are *ignored*, asserted as *hard constraints*, or *tracked* in a fault flag
- Supports symbolic references with policy control via `SymRefPolicy` (`CLOSED` restricts references to existing objects that have been allocated thus far during execution; `OPEN` allows symbolic references to non-existent objects)

### `MachineConfig: object`

Configuration for the symbolic state machine, controlling solver behavior, fault handling, and symbolic reference policies. Optimizes the symbolic execution process through Z3 solver configuration and tuning parameters.

#### Public API

- **Fields**:
  - ~~`allow_type_unions: bool` - Whether to allow type unions in object instances~~ (default `True`, currently **unused**)
  - `fault_mode: FaultMode` - How to handle faults (`IGNORE`, `AVOID`, `STORE`; default `AVOID`)
  - `literal_substitution_enabled: bool` - Enables caching and substitution of literal values for optimization (default `True`)
  - `solver_timeout: int | None` - Timeout for Z3 solver in milliseconds (default `None` - unlimited)
  - `solver_try_count: int` - Maximum number of solver check attempts before giving up (default `10`)
  - `solver_tuning: dict[str, object]` - Additional Z3 solver tuning parameters including `qi.max_multi_patterns`, `rewrite_patterns`, `threads`, and `threads.max_conflicts`
  - `symbolic_ref_policy: SymRefPolicy` - Policy for symbolic references (`CLOSED` restricts to existing objects, `OPEN` allows references to non-existent objects; default `CLOSED`)

- **Methods**: (none)

#### Implementation details

`MachineConfig` is marked `@final` and initializes with sensible defaults: `FaultMode.AVOID` to reject fault conditions, `SymRefPolicy.CLOSED` to restrict symbolic references to existing objects, and `literal_substitution_enabled=True` to cache literal values for read optimization. The default solver tuning configures `qi.max_multi_patterns` to 40, enables `rewrite_patterns`, sets thread count to half the CPU cores, and sets `threads.max_conflicts` to 2 billion.

### `SymbolicStateMachineStatistics: object`

Tracks statistics about objects created during symbolic execution; maintains counts and type information for arrays, sets, maps, transforms, and structures that were allocated during instruction execution.

#### Public API

- **Fields**:
  - `arrays: dict[int, PrimitiveTypeInfo]` - Maps object reference IDs to their element types for arrays
  - `sets: dict[int, PrimitiveTypeInfo]` - Maps object reference IDs to their element types for sets
  - `maps: dict[int, tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]]` - Maps object reference IDs to their (key_type, value_type) tuples for maps
  - `transforms: dict[int, tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]]` - Maps object reference IDs to their (key_type, value_type) tuples for transforms
  - `structures: dict[int, StructureTypeInfo]` - Maps object reference IDs to their structure type information

- **Methods**:
  - `resolve_ref_type(reference: int | None) -> TypedReferenceTypeInfo | None` - Resolves a reference ID to its corresponding typed reference type (array, set, map, transform, or structure wrapped in a reference)

#### Implementation details

`SymbolicStateMachineStatistics` is marked `@final` and initialized empty; all dictionaries are populated incrementally as objects are allocated during symbolic execution via `_register_new_*` methods on the state machine. The `resolve_ref_type` method performs a sequential lookup across arrays, sets, maps, transforms, and structures to find the type information for a given reference ID, wrapping the result in `ref()` to produce a `TypedReferenceTypeInfo`; it returns `None` if the reference is unknown or not found in any pool, enabling the caller to safely handle unregistered references.

### `VersionedVariable: object`

Represents a variable with versioning for SSA semantics; tracks different versions of the same variable during symbolic execution; each write operation increments the version counter. Used by `VariableCache` to resolve expressions to their current values.

#### Public API

- **Fields**:
  - `variable: VariableInfo` - The variable's type and name information
  - `version: int` - Current version number (starts at 0, incremented on each write)

- **Methods**:
  - `clone() -> VersionedVariable` - Creates a new copy with the same variable reference and current version number
  - `increment() -> VersionedVariable` - Increments the version counter and returns self for chaining

### `VariableCache: object`

Manages the mapping of versioned variables to Z3 constant expressions; translates versioned variables into solver-friendly symbolic references; maintains a cache of expressions keyed by `variable_name:version` strings.

#### Public API

- **Fields**:
  - `refs: dict[str, z3.ExprRef]` - Maps `variable_name:version` strings to Z3 constant expressions, lazily creating fresh `z3.Const` entries keyed by the full name including variable type information

- **Methods**:
  - `resolve(vv: VersionedVariable, version: int | None = None) -> z3.ExprRef` - Resolves a versioned variable to its Z3 constant expression; uses current version if no explicit version provided

#### Implementation details

Creates fresh Z3 constants on first access for each variable+version combination

## Module-level functions

- `typeid_name_for_structure(name: str) -> str` - Generates a type ID string for a given structure name
- `typeid_name_for_array(itype: TypeInfo) -> str` - Creates a type ID for an array type in the format `array<item_type_name>`
- `typeid_name_for_set(itype: TypeInfo) -> str` - Creates a type ID for a set type in the format `set<item_type_name>`
- `typeid_name_for_map(ktype: TypeInfo, vtype: TypeInfo) -> str` - Creates a type ID for a map type in the format `map<key_type_name,value_type_name>`
- `typeid_name_for_transform(ktype: TypeInfo, vtype: TypeInfo) -> str` - Creates a type ID for a transform type in the format `transform<key_type_name,value_type_name>`

---

*AI usage disclosure: this document was generated by a large language model, all text has been validated and edited by a human developer.*
