# micro_svm.type_hierarchy

## Overview

### Summary

`TypeHierarchyResolver` builds and analyzes class hierarchy relationships within program specifications, resolving method implementations, field origins, and virtual call targets across inheritance hierarchies. It identifies abstract classes and methods, propagates implementations through parent classes, and provides comprehensive queries for method and field resolution following Python-like method resolution order (MRO).

### Purpose

The module provides a complete type hierarchy analysis system that enables symbolic execution to handle virtual method calls, field access across inheritance chains, and abstract class detection. It resolves which concrete implementation should be invoked for a given method call based on the runtime type of the object, following the inheritance hierarchy and respecting method overriding rules.

### Role in the Project

This module is an important component of the symbolic virtual machine's path enumeration phase, specifically handling virtual method calls during program exploration. When the path exploration mechanism encounters a `CallVirtual` CFG node, it uses `TypeHierarchyResolver` to determine all possible concrete implementations based on the object's type hierarchy. This enables the system to explore all valid call paths through polymorphic code.

The module also supports field origin resolution, which is necessary for correctly tracking field values across inheritance hierarchies.

### Contracts

- The `GlobalContext` instance passed to `TypeHierarchyResolver` must have been fully populated with structure definitions and function implementations before calling `analyze_structure_hierarchy()`.
- Structure names and method names are case-sensitive and must match exactly.
- Method resolution follows Python-like MRO: implementations are searched in parent classes in the order they are declared in the `parents` list of `StructureTypeInfo`.
- Field shadowing is handled by checking parent classes first; if a field is redeclared in a child class, the parent's field origin is returned.
- Circular structure type dependencies will raise a `ValueError` during hierarchy analysis.
- Abstract classes (those with any abstract methods) cannot be instantiated and thus cannot serve as exact type guards for virtual calls.

## Classes

### `TypeHierarchyResolver: object`

Core class responsible for building and querying class hierarchy relationships within program specifications. Maintains internal data structures for subclasses, method origins, abstract methods, and field origins, and provides methods for resolving virtual calls, field access, and method implementations across inheritance hierarchies.

#### Public API

- **Fields:**
  - `abstract_methods: set[str]` - Set of method signatures that are declared but have no implementation. Used to identify abstract methods.
  - `abstract_structures: set[str]` - Set of structure names that have at least one abstract method. These structures cannot be instantiated.
  - `method_origin: dict[str, str]` - Mapping from fully qualified method signature `class.method` to the implementation function name. Resolved after hierarchy analysis.
  - `root_structures: set[str]` - Set of structure names that have no parent structures (roots of the hierarchy).
  - `subclasses: dict[str, set[str]]` - Mapping from parent structure name to set of immediate child structure names. Built during hierarchy analysis.

- **Methods:**
  - `analyze_structure_hierarchy() -> None` - Main entry point for hierarchy analysis. Performs three-phase analysis: builds hierarchy, identifies abstract methods, and propagates implementations.
  - `get_all_fields(structure_name: str) -> dict[str, str]` - Returns all fields (including inherited ones) for a structure, mapping field names to their origin structure names.
  - `get_all_methods(structure_name: str) -> dict[str, tuple[str, str]]` - Returns all concrete methods (including inherited ones) for a structure, mapping `implementation_name => (declaration_struct_name, method_name)`.
  - `get_all_parents_of(structure_name: str) -> set[str]` - Returns all parent structures (ancestors) of the given structure.
  - `get_field_origin(starting_struct: str, field: str) -> str` - Returns the structure name where a field was first declared, following the inheritance hierarchy.
  - `get_virtual_call_targets(structure_name: str, method_name: str) -> dict[str, str]` - Returns a dictionary mapping concrete structure names to their method implementations for a given virtual call. Only includes non-abstract structures.
  - `reset() -> None` - Clears all internal data structures, resetting the resolver to its initial state.

#### Implementation details

The hierarchy analysis follows a multi-pass approach:

1. **Hierarchy Building**: Uses breadth-first search (BFS) starting from root structures to propagate parent relationships. This builds the `_all_parents` mapping and detects circular dependencies by tracking visited structures during traversal.

2. **Abstract Method Identification**: Scans all structures to identify methods that are declared but have no implementation. Methods without implementations are marked as abstract, and structures containing any abstract methods are marked as abstract structures.

3. **Implementation Propagation**: For each structure, recursively searches parent classes to find concrete implementations of all methods. This populates the `method_origin` mapping following Python-like MRO.

4. **Abstract Structure Resolution**: After propagation, identifies structures that still have unresolved methods (no implementation found in any parent), marking them as abstract structures.

Method resolution uses depth-first search with cycle detection to find the first concrete implementation in the inheritance chain. Field origin resolution similarly checks parent classes first to handle field shadowing correctly.

The module intentionally defers field propagation to on-demand queries to avoid storing excessive data.

## Module-level functions

None.

---

*AI usage disclosure: this document was generated by a large language model, all text has been validated and edited by a human developer.*
