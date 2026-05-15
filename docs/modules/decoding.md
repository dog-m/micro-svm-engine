# micro_svm.decoding

## Overview

### Summary

`ModelDecoder` interprets symbolic execution results from the `SymbolicStateMachine` by extracting concrete values from SMT solver models. It handles primitive types, container types (arrays, sets, maps, transforms), and structure instances, building a complete state representation with reference tracking and dependency analysis. `StateIntermediateDescription.analyze()` performs an iterative traversal starting from all local and global variables, building a reachability map that associates each reference with its sources and type information.

### Purpose

The `micro_svm.decoding` module serves as the bridge between symbolic modelling and concrete state representations. It extracts actual values from symbolic expressions using the solver's model, handles complex data structures including nested containers and object references, and provides a comprehensive description of the program state that can be used for checking program correctness or defect detection. The module is essential for converting abstract symbolic states into concrete, actionable information.

### Role in the Project

The decoding module receives symbolic execution results from `SymbolicStateMachine` and transforms them into concrete Python objects that represent the actual program state. This functionality is used by `DefectAnalyzer` for analyzing failing paths and produce minimal counterexamples. The module works closely with `GlobalContext` for type information, `TypeHierarchyResolver` for resolving object types, and `SymbolicStateMachine` for accessing solver models and execution statistics.

### Contracts

The module expects the following from its dependencies:

- **GlobalContext**: Provides type information for structures, global variables, and type resolution
- **TypeHierarchyResolver**: Supplies class hierarchy relationships and field origin information
- **SymbolicStateMachine**: Must have a valid solver model accessible via `_last_model` and execution statistics via `statistics.resolve_ref_type()`

The module assumes that all references are represented as `integer`s and that container sizes are explicitly tracked in the symbolic state.

## Classes

### `ModelDecoder: object`

Main decoder class that extracts concrete values from symbolic execution models and performs type-specific decoding for various data structures.

#### Public API

- **Fields:**
  - `ctx: GlobalContext` - Global context providing type information and structure definitions
  - `machine: SymbolicStateMachine` - Symbolic state machine providing solver model and execution statistics
  - `th_resolver: TypeHierarchyResolver` - Type hierarchy resolver for class relationships and field origins

- **Methods:**
  - `decode_value(source: z3.ExprRef, type: TypeInfo) -> ValueType` - Decodes a primitive value from a symbolic expression
  - `decode_reference(ref: z3.ExprRef | int, type: TypeInfo, version: int | None) -> object` - Decodes a reference to a container or structure instance
  - `decode(vv: VersionedVariable, *, version: int | None = None, resolve_reference: bool = False) -> object` - Main decoding entry point for versioned variables
  - `infer_reference_type(object_ref: z3.ExprRef | int) -> TypedReferenceTypeInfo | None` - Infers the type of an untyped reference based on type ID patterns and structure hierarchy

#### Implementation details

The `ModelDecoder` class uses a model-based approach where all symbolic expressions are evaluated against the solver's concrete model. For primitive types, values are extracted directly using `model.eval()` with model completion enabled. For more complex types (containers and structures), the decoder performs a type-specific dispatch to specialized decoding methods.

The `_get_basic_container_types()` method lazily initializes a cache of basic container types (arrays, sets, maps, transforms) for **all possible** primitive type combinations, enabling efficient type inference for untyped references. This cache is built on-demand and reused across all decoding operations.

Reference decoding follows a multi-step process: first checking for null references, then determining the container size, and finally dispatching to the appropriate container-specific decoder. The `decode_reference()` method handles all reference types including structures, arrays, sets, maps, and transforms.

Type inference for untyped references uses a heuristic approach: it first checks for basic container type patterns in the type ID, then searches the structure hierarchy for matching type declarations, preferring structures with more total number of parent classes (more specific types take precedence).

### `ValueSource: ABC`

Abstract base class representing different sources of values in the program state. Subclasses provide concrete implementations for specific value retrieval patterns.

#### Public API

- **Methods:**
  - `is_grounding(self) -> bool` - Returns `True` if this source represents a direct variable reference that can be used as a grounding point
  - `to_instructions(self, ref_handles: dict[int, VariableRead]) -> list[Instruction]` - Converts the source into a sequence of instructions for accessing the value

#### Implementation details

The `is_grounding()` method identifies sources that represent direct variable references, which are useful for building grounding points and more efficient for specifying additional constraints on in symbolic execution. The `to_instructions()` method translates source information into executable instructions, using `ref_handles` to map reference IDs to variable read operations.

### `VariableSource: ValueSource`

Represents a local or global variable as a value source.

#### Public API

- **Fields:**
  - `is_local: bool` - `True` if the variable is local, `False` if it's a global variable
  - `name: str` - The variable name

#### Implementation details

This class provides a simple wrapping of variable references for use in dependency tracking and instruction generation. The `is_grounding()` method returns `True` since variable references can serve as grounding points for symbolic execution.

### `FieldSource: ValueSource`

Represents a field within a structure instance as a value source.

#### Public API

- **Fields:**
  - `field_name: str` - The name of the field being accessed
  - `object_ref: int` - The reference to the structure instance
  - `structure_name: str` - The name of the structure type

#### Implementation details

This class is used to track field access patterns during dependency analysis. The `to_instructions()` method generates instructions that first read the structure instance and then extract the specified field.

### `ArrayElementSource: ValueSource`

Represents an specific element within an array as a value source.

#### Public API

- **Fields:**
  - `container_ref: int` - The reference to the array container
  - `index: int` - The index of the element to access
  - `size_t: PrimitiveTypeInfo` - The type of the index (`integer`)

#### Implementation details

This class is used to track array element access patterns during dependency analysis. The `to_instructions()` method generates instructions that read the source element at the specified index in the container.

### `SetElementSource: ValueSource`

Represents an *arbitrary* element within a set as a value source.

#### Public API

- **Fields:**
  - `container_ref: int` - The reference to the set container

#### Implementation details

This class provides a *weak assumption* that the desired element in the set can be accessed. The `to_instructions()` method generates instructions to perform a `SetOperation.ANY_ITEM` to retrieve an arbitrary element.

### `MapKeySource: ValueSource`

Represents an *arbitrary* key within a map as a value source.

#### Public API

- **Fields:**
  - `container_ref: int` - The reference to the map container
  - `kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]` - The key-value type pair
  - `selector: ValueType` - A selector value used in instruction generation

#### Implementation details

This class provides a *weak* assumption that the desired key from a map can be accessed. The `to_instructions()` method generates instructions to perform a `MapOperation.ANY_KEY` to retrieve an arbitrary key.

### `MapValueSource: ValueSource`

Represents an *arbitrary* value within a map as a value source.

#### Public API

- **Fields:**
  - `container_ref: int` - The reference to the map container
  - `kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]` - The key-value type pair
  - `selector: ValueType` - A selector value used in instruction generation

#### Implementation details

This class provides a *weak* assumption that the desired value from a map can be accessed. The `to_instructions()` method generates instructions to perform a `MapOperation.ANY_VALUE` to retrieve an arbitrary value.

### `TransformKeySource: ValueSource`

Represents a key-value pair where the key matches a selector value in a transform container as a value source.

#### Public API

- **Fields:**
  - `container_ref: int` - The reference to the transform container
  - `kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]` - The key-value type pair
  - `selector: ValueType` - The selector value to match in the key

#### Implementation details

This class uses a *strong* assumption that the key in the transform pair matches the selector value. The `to_instructions()` method generates instructions that:

1. Allocate two anonymous temporary variables (which is the underlying implementation for `PushSymbolic`):
    - a pure symbolic "key" handle
    - a handle for managing the "value" selector
2. Bind the value selector to the value handle variable
3. Perform `GET` operation on the transform instance using symbolic "key" handle
4. Add a constraint: the returned value should match the provided concrete selector
5. Return "key" handle as the primary value source

### `TransformValueSource: ValueSource`

Represents an *arbitrary* value in a transform container as a value source.

#### Public API

- **Fields:**
  - `container_ref: int` - The reference to the transform container
  - `kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]` - The key-value type pair
  - `selector: ValueType` - A selector value used in instruction generation

#### Implementation details

This class provides a *weak* assumption that the desired value from a transform can be accessed. The `to_instructions()` method generates instructions to perform a `TransformOperation.GET` with an arbitrary key to retrieve a value.

### `ReferenceInfo: dataclass`

Tracks information about a reference, including its type and all sources that lead to it.

#### Public API

- **Fields:**
  - `sources: list[ValueSource]` - All sources that point to the same object instance
  - `type: TypeInfo` - Referenced object instance type

- **Methods:**
  - `get_grounding() -> ValueSource | None` - Returns the first grounding source if available, useful for finding the primary origin of a reference

#### Implementation details

The `ReferenceInfo` class is used by `StateIntermediateDescription.analyze()` to build a reachability map where each object is associated with model sources that refer to it. This information helps identify which objects are reachable from which variables.

### `StateIntermediateDescription: object`

Analyzes a symbolic execution state and produces a comprehensive description of all reachable objects, their types, and their relationships.

#### Public API

- **Fields:**
  - `collection_count: int` - Total number of container instances decoded from the concrete solver model
  - `collection_sizes: dict[int, int]` - Mapping from container references to their sizes
  - `reachability_map: dict[int, ReferenceInfo]` - Mapping from reference IDs to their type and sources
  - `structure_count: int` - Total number of structure instances decoded
  - `structure_instances: set[int]` - Set of all structure instance references

- **Methods:**
  - `analyze(m: SymbolicStateMachine, local_variables: list[VariableInfo], th_resolver: TypeHierarchyResolver, context: GlobalContext) -> StateIntermediateDescription` - Static factory method that performs the complete state analysis
  - `get_value(identifier: str) -> InitializerValueType` - Retrieves a value associated with the specified identifier/name
  - `is_container(ref: int) -> bool` - Checks if a reference ID corresponds to a container-like object (array, set, map, or transform)

#### Implementation details

The `StateIntermediateDescription.analyze()` method performs iterative traversal starting from all local and global variables. For each reference encountered, it decodes the entire object graph reachable from that reference, building a comprehensive dependency map.

For structures, the decoder recursively decodes all fields, including inherited fields from parent classes.
For containers, it decodes all elements and tracks container sizes and validates that the decoded container size matches expectations, printing a warning if discrepancies are found.

The analysis maintains a `unique_refs` set to avoid processing the same reference multiple times, which is important for handling cyclic references (e.g., objects containing references to themselves or to each other).

## Module-level functions

None.

---

*AI usage disclosure: this document was generated by a large language model, all text has been validated and edited by a human developer.*
