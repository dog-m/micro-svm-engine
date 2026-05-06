# micro_svm.types

## Overview

### Summary

`TypeInfo` and its subclasses define the type system for the symbolic virtual machine, mapping program types to Z3 solver types and providing conversion utilities. The module supports primitive types (boolean, integer variants, real, string, char, reference), collection types (arrays, sets, maps, transforms), and user-defined structures with fields and inheritance. `PRIMITIVE_TYPES` list all primitive type information objects.

### Purpose

The `micro_svm.types` module serves as the foundational type system for the symbolic virtual machine, bridging the gap between high-level program types and low-level Z3 solver expressions. It provides a type-safe abstraction layer that enables the symbolic execution engine to reason about program state, validate type constraints, and generate appropriate solver expressions for type-specific operations. The module's core responsibility is to define type metadata, conversion functions, and type relationships that are used throughout the symbolic execution pipeline.

### Role in the Project

This module is central to the symbolic virtual machine's operation, providing the type information that drives multiple subsystems:

- **Global Context**: Type definitions are registered in `GlobalContext` to describe user-defined structures and classes, including their fields, parent relationships, and method signatures
- **Symbolic Execution**: Type information is used during path exploration to validate type constraints, resolve virtual calls via `TypeHierarchyResolver`, and generate appropriate solver expressions for type-specific operations
- **Serialization**: Type information is serialized to JSON format to describe program specifications and target states

The type system is tightly integrated with the Z3 solver, where each type maps to an appropriate Z3 sort (e.g., `z3.BoolSort()` for booleans, `z3.IntSort()` for integers, `z3.ArraySort()` for collections).

### Contracts

- **Type Hierarchy**: All type information objects must be instances of `TypeInfo` or its subclasses. The type system enforces that references cannot point to primitive types
- **Z3 Integration**: Each type must provide a valid Z3 sort reference via the `z3_sort` attribute. The `default_value` attribute must be a valid Z3 expression representing the type's zero value
- **Collection Constraints**: Collection types (`ArrayTypeInfo`, `SetTypeInfo`, `MapTypeInfo`, `TransformTypeInfo`) require primitive item types and use Z3 array sorts with boolean presence indicators
- **Structure Constraints**: Structure types must have valid parent structure names and field definitions. Field types must be primitive types, and field names must be unique within their structure
- **Reference Constraints**: `UntypedReferenceTypeInfo` represents opaque generic references (serialized as `ref`). `KnownReferenceTypeInfo` represents typed references and must target non-primitive types. Both use integer representation

## Classes

### `TypeInfo: object`

Base class for all type information objects. Provides common attributes and abstract methods that must be implemented by concrete type classes.

#### Public API

- **Fields:**
  - `default_value: z3.ExprRef | None` - Z3 expression representing the type's default/zero value
  - `name: str` - Human-readable name of the type
  - `z3_sort: z3.SortRef` - Z3 solver sort reference for this type

- **Methods:**
  - `is_collection() -> bool` - Returns `False` (baseline for all subclasses)
  - `is_primitive() -> bool` - Returns `False` (baseline for all subclasses)
  - `is_reference() -> bool` - Returns `False` (baseline for all subclasses)
  - `wrap_primitive(value: object) -> z3.ExprRef` - Converts a Python value to a Z3 expression for this type. Raises `NotImplementedError` for non-primitive types

#### Implementation details

`TypeInfo` serves as an abstract base class that defines the type system's interface. All concrete type classes inherit from this base and implement the type-specific behavior through the `wrap_primitive()` method, which is responsible for converting Python runtime values to Z3 solver expressions.

The `is_primitive()`, `is_reference()`, and `is_collection()` methods provide type classification that is used throughout the symbolic execution engine for type checking and constraint generation. These methods follow a simple inheritance-based design where each concrete type overrides the appropriate method to return `True`.

### `PrimitiveTypeInfo: TypeInfo`

Concrete type class for primitive types. Wraps a Z3 sort with conversion functions to bridge Python values and Z3 expressions.

#### Public API

- **Fields:**
  - `convertor: Callable[[object], z3.ExprRef]` - Function that converts Python values to Z3 expressions for this type
  - `default_value: z3.ExprRef` - Z3 expression for the type's zero value
  - `default_raw: object` - Python value representing the type's zero value (e.g., `False` for booleans, `0` for integers)
  - `name: str` - Type name
  - `z3_sort: z3.SortRef` - Z3 sort reference

- **Methods:**
  - `__str__() -> str` - Returns the type name
  - `is_primitive() -> bool` - Returns `True`
  - `wrap_primitive(value: object) -> z3.ExprRef` - Converts a Python value to a Z3 expression using the `convertor` function (overrides `TypeInfo.wrap_primitive()`)

#### Implementation details

`PrimitiveTypeInfo` encapsulates the complete type information for primitive types, including both the Z3 representation and Python runtime representation. The `convertor` callable enables conversion between Python values and Z3 expressions. This allows the symbolic execution engine to work with concrete Python values during specification handling and convert them to symbolic Z3 expressions during execution.

The `default_raw` attribute provides a Python-level zero value that can be used for initialization and comparison purposes outside of the Z3 solver context.

### `UntypedReferenceTypeInfo: PrimitiveTypeInfo`

Represents untyped/generic references that are serialized as `ref` in the specification format. Uses integer representation internally.

#### Public API

- **Fields:**
  - `convertor: Callable[[object], z3.ExprRef]` - References `z3.IntVal`
  - `default_value: z3.ExprRef` - Always `z3.IntVal(0)`
  - `default_raw: object` - Always `0`
  - `name: str` - Always `ref`
  - `z3_sort: z3.SortRef` - Always `z3.IntSort()`

- **Methods:**
  - `__str__() -> str` - Returns just `ref`
  - `is_reference() -> bool` - Returns `True`

#### Implementation details

`UntypedReferenceTypeInfo` represents references are treated as generic/opaque object handles that can be compared and assigned but type of which isn't needed to be statically determined prior to program "execution". These references are serialized as the string `"ref"` in the JSON specification format and use integer representation internally for solver operations.

### `ArrayTypeInfo: TypeInfo`

Represents array collections with a fixed element type and size.

#### Public API

- **Fields:**
  - `default_value: z3.ExprRef | None` - Always `None`
  - `index_type: PrimitiveTypeInfo` - `integer` type for array indices
  - `item_type: PrimitiveTypeInfo` - Element type of the array
  - `name: str` - Always `array`
  - `z3_sort: z3.SortRef` - Z3 array sort with integer index type and element type

- **Methods:**
  - `__str__() -> str` - Returns `array<{item_type}>` (e.g., `array<integer>`)
  - `is_collection() -> bool` - Returns `True`

#### Implementation details

`ArrayTypeInfo` represents variable-sized arrays where each element has the same type. The Z3 representation uses an array sort with integer indices. The `item_type` must be a primitive type, as collections can only contain primitive values in this type system.

The class uses Z3's array sort semantics where array access is represented as `select(select(typed_array_pool, array_ref), index)` and array updates are represented as a sequence of quantifier expressions on that array, "assigning" elements over to an "updated" instance. This approach demonstrated better performance compared to using `store(...)` expressions.

The underlying array is *effectively* infinite with respect to the `index_type` domain (default is `integer`). Array size starts off as `0` and should be managed manually by the user specification/program model.

### `TypedReferenceTypeInfo: PrimitiveTypeInfo`

Represents typed references that point to specific structure or class types.

#### Public API

- **Fields:**
  - `convertor: Callable[[object], z3.ExprRef]` - `z3.IntVal`
  - `default_value: z3.ExprRef` - Always `z3.IntVal(0)`
  - `default_raw: object` - Always `0`
  - `name: str` - Always `ref`
  - `target_type: TypeInfo` - The type of the object that this reference points to
  - `z3_sort: z3.SortRef` - `z3.IntSort()`

- **Methods:**
  - `__str__() -> str` - Returns `ref<{target_type}>` (e.g., `ref<array<integer>>` or `ref<struct="std.List">`)
  - `is_reference() -> bool` - Returns `True`

#### Implementation details

`TypedReferenceTypeInfo` represents references with known object types, enabling type-safe operations and validation. Unlike untyped references, these ones carry type information that can be used during program path exploration to validate type constraints and resolve virtual calls.

The class enforces a constraint that references cannot point to primitive types.

### `SetTypeInfo: TypeInfo`

Represents sets as arrays (item = key/index) with boolean presence indicators (value = is present).

#### Public API

- **Fields:**
  - `default_value: z3.ExprRef | None` - `None`
  - `item_type: PrimitiveTypeInfo` - Element type of the set
  - `name: str` - Always `set`
  - `z3_sort: z3.SortRef` - Z3 array sort with element type and boolean presence indicators

- **Methods:**
  - `__str__() -> str` - Returns `set<{item_type}>` (e.g., `set<integer>`)
  - `is_collection() -> bool` - Returns `True`

#### Implementation details

`SetTypeInfo` represents sets using a sparse array representation where each element is paired with a boolean flag indicating its presence. This approach leverages Z3's array sort capabilities to represent set operations efficiently. The Z3 sort is `ArraySort(item_type, BoolSort())`, where the boolean value indicates whether the element is present in the set.

Set operations like membership testing are represented as checking the boolean presence indicator, and set insertion is represented as setting the boolean to `True`. This representation enables efficient symbolic reasoning about set operations while maintaining the mathematical properties of sets.

### `MapTypeInfo: TypeInfo`

Represents maps as 2D-arrays with key-value pairs and boolean presence indicators (similar to sets).

#### Public API

- **Fields:**
  - `default_value: z3.ExprRef | None` - Always `None`
  - `key_type: PrimitiveTypeInfo` - Key type of the map
  - `kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]` - Tuple of `key_type + value_type`
  - `name: str` - Always `map`
  - `value_type: PrimitiveTypeInfo` - Value type of the map
  - `z3_sort: z3.SortRef` - Z3 array sort

- **Methods:**
  - `__str__() -> str` - Returns `map<{key_type}, {value_type}>` (e.g., `map<string, integer>`)
  - `is_collection() -> bool` - Returns `True`

#### Implementation details

`MapTypeInfo` represents mappings using a sparse 2D-array representation where each key-value pair is paired with a boolean presence indicator. The Z3 sort is `ArraySort(key_type, ArraySort(value_type, BoolSort()))`, which enables efficient representation of map operations.

Map operations like key lookup (`map[key]`) are represented as checking the presence indicator for the key and retrieving the associated symbolic value (i.e., "Does there *exist* a value that is *associated* with that key?"). Map insertion and deletion are represented by setting the presence indicator to `True` or `False`, respectively and updating the container size accordingly. This representation allows the symbolic execution engine to reason about map operations while maintaining the mathematical properties of maps (thou "transform"-type of objects may offer better performance in some cases in exchange for handling container size updates manually).

### `TransformTypeInfo: TypeInfo`

Represents transforms as functions from keys to values without size constraints.

#### Public API

- **Fields:**
  - `default_value: z3.ExprRef | None` - Always `None`
  - `key_type: PrimitiveTypeInfo` - Key type of the transform
  - `kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]` - Tuple of `key_type + value_type`
  - `name: str` - Always `transform`
  - `value_type: PrimitiveTypeInfo` - Value type of the transform
  - `z3_sort: z3.SortRef` - Z3 array sort

- **Methods:**
  - `__str__() -> str` - Returns `transform<{key_type}, {value_type}>` (e.g., `transform<string, integer>`)
  - `is_collection() -> bool` - Returns `False`

#### Implementation details

`TransformTypeInfo` represents transforms as *dynamic* functions from keys to values without size constraints or presence indicators. Unlike maps, transforms are assumed to be total functions where every key has a defined value. The Z3 sort is `ArraySort(key_type, value_type)`, which is simpler than the map representation.

Transforms are useful for representing mathematical functions or transformations where the domain and codomain are known but the size is not. The symbolic execution engine uses this type information to generate appropriate solver expressions for transform operations.

### `FieldInfo: object`

Represents a field in a user-defined structure or class.

#### Public API

- **Fields:**
  - `name: str` - Field name
  - `tags: set[str]` - Set of string tags for the field (e.g., `{ "public", "my-annotation" }`)
  - `type: PrimitiveTypeInfo` - Field type (must be a primitive type)

#### Implementation details

`FieldInfo` provides a simple representation of a field in a structure or class. The field type must be a primitive type, as the type system does not support nested structures or complex types for fields (use references for that). The tags attribute enables additional metadata about the field that can be used for reflection, serialization, or other purposes.

### `StructureTypeInfo: TypeInfo`

Represents user-defined structures or classes with fields, methods, and inheritance.

#### Public API

- **Fields:**
  - `default_value: z3.ExprRef` - same as `reference.default_value`
  - `fields: dict[str, FieldInfo]` - Dictionary mapping field names to `FieldInfo` objects
  - `methods: dict[str, str]` - Dictionary mapping method names to full method signatures (directly bound)
  - `name: str` - Always `struct`
  - `parents: list[str]` - List of parent structure names (empty list for root structures)
  - `static_methods: dict[str, str]` - Dictionary mapping static method names to full method signatures (directly bound)
  - `structure_name: str` - Structure name (non-empty)
  - `z3_sort: z3.SortRef` - Same as `reference.z3_sort`

- **Methods:**
  - `__str__() -> str` - Returns `struct={structure_name!r}` (e.g., `struct="std.List"`)

#### Implementation details

`StructureTypeInfo` represents user-defined structures or classes in the type system. It supports inheritance through the `parents` list, which follows Python's method resolution order (MRO) where parent classes are searched in declaration order.

The class maintains separate dictionaries for `methods` and `static_methods`, enabling both instance and static method definitions. Method signatures are stored as full strings for direct binding, which simplifies method lookup during program path exploration.

## Module-level functions

- `field(name: str, type: TypeInfo, *, tags: set[str] | None = None) -> FieldInfo` - Creates a `FieldInfo` for the given name and type. The type must be a primitive type. Returns a `FieldInfo` instance with the specified name, type, and tags (defaults to an empty set if not provided).
- `array(element_type: TypeInfo) -> ArrayTypeInfo` - Creates an `ArrayTypeInfo` for the given element type. The element type must be a primitive type. Returns an `ArrayTypeInfo` instance with the element type and integer index type.
- `map_of(key: PrimitiveTypeInfo, value: PrimitiveTypeInfo) -> MapTypeInfo` - Creates a `MapTypeInfo` for the given key and value types. Both types must be primitive types. Returns a `MapTypeInfo` instance representing a map from keys to values.
- `ref(type: TypeInfo) -> TypedReferenceTypeInfo` - Creates a `TypedReferenceTypeInfo` for the given target type. The target type must not be a primitive type. Returns a `TypedReferenceTypeInfo` instance representing a reference to the specified type.
- `set_of(item_type: PrimitiveTypeInfo) -> SetTypeInfo` - Creates a `SetTypeInfo` for the given item type. The item type must be a primitive type. Returns a `SetTypeInfo` instance representing a set of the specified element type.
- `transform_of(key: PrimitiveTypeInfo, value: PrimitiveTypeInfo) -> TransformTypeInfo` - Creates a `TransformTypeInfo` for the given key and value types. Both types must be primitive types. Returns a `TransformTypeInfo` instance representing a transform from keys to values.

---

*AI usage disclosure: this document was generated by a large language model, all text has been validated and edited by a human developer.*
