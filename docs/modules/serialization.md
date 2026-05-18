# micro_svm.serialization

## Overview

### Summary

The serialization module provides bidirectional JSON-based serialization and deserialization capabilities for program specifications and program states in the symbolic virtual machine. It encodes and decodes type hierarchies, global variables, functions, control flow graphs, and program execution states, enabling persistent storage and loading of program analysis artifacts. The module uses a recursive encoding strategy for complex data structures and provides both compact and formatted JSON output formats.

### Purpose

The primary purpose of this module is to enable the persistent storage and retrieval of program specifications and execution states. The module supports two distinct domains: library specification serialization (types, functions, CFGs) and program state serialization (global variables, object instances, expected objects).

### Role in the Project

The serialization module bridges the gap between runtime program analysis and external storage, allowing the symbolic virtual machine to:

- Save program specifications created via the compiler API for later use
- Store program states generated during path exploration for defect detection
- Provide a human-readable JSON format for debugging and analysis
- Archiving program specifications for reproducible experiments

The module works closely with `GlobalContext` for specifications and `ProgramState` for execution states, and is used by `DefectAnalyzer` for state management.

### Contracts

The module expects well-formed input data and makes several assumptions:

- **Types**: All type-related information must be properly encoded with a `_` discriminator field indicating the type kind ('ref', 'structure', 'array', 'set', 'map', 'transform', or primitive type names)
- **CFG node IDs**: All CFG nodes must have unique string identifiers (default is a hexadecimal format like "#0000") that are used for cross-referencing
- **Instructions**: All instructions must have a `_` discriminator field matching their class name
- **State validation**: Program state loading validates that values match their declared types, raising `ValueError` for mismatches
- **Object reachability**: When `prune=True` (default), unreachable objects are automatically removed from loaded states
- **Entity registration**: De-serialization implementation is tightly coupled with how `GlobalContext`/specification context registers user functions and structures. It is critical to keep them in sync with one another.

## Classes

### `TypeEncoder: object`

Encodes type information into JSON-compatible dictionaries. Handles all type system constructs including primitive types, reference types, structures, arrays, sets, maps, and transforms.

#### Public API

- **Fields:** (none)

- **Methods:**
  - `encode_structure(struct: StructureTypeInfo) -> dict[str, object]` - Encodes a structure type definition including name, parent classes, and fields
  - `encode_type_reference(type: TypeInfo | None) -> dict[str, object] | None` - Encodes type-related information, handling polymorphic types like primitives, references, arrays, sets, maps, and transforms

#### Implementation details

The encoder uses a recursive approach for nested type info objects, particularly for reference types (`TypedReferenceTypeInfo` and `UntypedReferenceTypeInfo`) which usually contain nested type information.

### `GlobalVariableEncoder: object`

Encodes global variable information including type, initializer value, and tags.

#### Public API

- **Fields:**
  - `type_encoder: TypeEncoder` - Reference to the type encoder used for encoding variable types

- **Methods:**
  - `encode_variable(variable: VariableInfo) -> dict[str, object]` - Encodes a global variable definition

#### Implementation details

Global variable encoding includes the initializer value which can be a boolean, number, string, list, list of pairs, or dictionary. The encoder delegates type encoding to the associated `TypeEncoder` instance, ensuring consistency with other parts of the serialization system.

### `NodeEnumerator: object`

Generates unique hexadecimal identifiers for CFG nodes during serialization. Uses a counter-based approach with hexadecimal formatting to create readable node IDs.

#### Public API

- **Fields:**
  - `counter: int` - Incrementing counter for generating new node IDs
  - `id_mapping: dict[int, str]` - Maps Python object IDs to serialized node IDs

- **Methods:**
  - `get_name_for(node: Node | None) -> str | None` - Returns a serialized node ID for a given CFG node, creating a new ID if the node hasn't been seen before

#### Implementation details

The enumerator uses `id(node)` as the key for mapping, which provides a unique identifier for each Python object. Node IDs are formatted as hexadecimal strings with 4 digits (e.g., "#0000" to "#ffff"), supporting up to 65536 unique nodes. This format is git-friendly and human-readable, making it easier to track changes in serialized CFGs.

### `FunctionEncoder: object`

Encodes function **metadata** including name, parameters, return type, static status, tags, and implementation details.

#### Public API

- **Fields:**
  - `enumerator: NodeEnumerator` - Reference to the node enumerator for encoding CFG entry points
  - `type_encoder: TypeEncoder` - Reference to the type encoder for encoding parameter and return types

- **Methods:**
  - `encode_function_header(func: FunctionInfo) -> dict[str, object]` - Encodes the function header including all metadata except the implementation body

#### Implementation details

Function encoding separates the header (metadata) from the implementation (CFG nodes). The implementation is encoded separately via `CfgEncoder.encode_function_body()`. The encoder uses the node enumerator to create cross-references between functions and their CFG nodes. Static methods are distinguished from instance methods through the `is_static` flag.

### `InstructionEncoder: object`

Encodes individual instructions into JSON-compatible dictionaries. Uses a dispatcher pattern with specialized encoder methods for each instruction type.

#### Public API

- **Fields:**
  - `encoders: dict[object, Callable[[Instruction], dict[str, object]]]` - Mapping from instruction classes to their encoder methods
  - `type_encoder: TypeEncoder` - Reference to the type encoder for encoding type information in instructions

- **Methods:**
  - `encode_instruction(inst: Instruction) -> dict[str, object]` - Encodes an instruction by dispatching to the appropriate encoder method based on the instruction's class

#### Implementation details

The encoder uses a dictionary-based dispatcher (`encoders`) that maps instruction classes to their respective encoding methods. This design allows for easy extension with new instruction types by simply adding a new entry to the dispatcher. Instructions that don't require special encoding (like `Pop`, `SubroutineEnter`, `SubroutineExit`) use a default encoder that returns an empty dictionary.

### `CfgEncoder: object`

Encodes control flow graphs (CFGs) into a flat node-based structure. Uses a recursive approach to traverse and encode the entire CFG.

#### Public API

- **Fields:** (none persistent)

- **Methods:**
  - `encode_function_body(func: FunctionInfo, cfg_nodes: dict[str, object]) -> None` - Encodes the implementation body of a function, populating the `cfg_nodes` dictionary with encoded nodes

#### Implementation details

The encoder uses an *iterative* traversal strategy that follows the `next` pointer in each node to encode the entire CFG as a linked list. Each node is encoded with its `_` discriminator field (the node class name) and additional type-specific fields. The `cfg_nodes` dictionary serves as a lookup table for cross-referencing nodes during encoding, with node IDs stored as keys. Special handling is provided for control flow nodes (`Switch`, `While`, `TryBlock`) which encode their branch targets *recursively*.

The encoder makes an assumption that the provided CFG is an acyclic, tree-like structure.

### `TypeDecoder: object`

Decodes type information from JSON dictionaries back into type objects.

#### Public API

- **Fields:**
  - `spec: GlobalContext` - Reference to the specification context where decoded types are registered

- **Methods:**
  - `decode_structure_body(info: dict[str, object]) -> None` - Decodes the fields of a structure after the header has been registered
  - `decode_structure_head(info: dict[str, object]) -> None` - Decodes the header of a structure (name, parents) without fields
  - `decode_type_reference(info: dict[str, object] | None) -> TypeInfo | None` - Decodes a type reference, handling all type kinds including references, structures, arrays, sets, maps, transforms, and primitives

#### Implementation details

The decoder uses a two-pass approach for structures: first decoding the header (name and parents) to register the structure, then decoding the fields in a second pass (methods would be added later during function de-serialization step). This allows `TypedReferenceTypeInfo` instances to point towards the structure being decoded. The decoder uses pattern matching on the `_` discriminator field to determine the type kind and dispatches to the appropriate constructor. Type info objects are decoded recursively, with opaque references (`ref` with no `item`) being a special case that doesn't expand to a target type.

### `GlobalVariableDecoder: object`

Decodes and registers global variable information from JSON dictionaries.

#### Public API

- **Fields:**
  - `spec: GlobalContext` - Reference to the specification context where decoded variables are registered
  - `type_decoder: TypeDecoder` - Reference to the type decoder for decoding variable types

- **Methods:**
  - `decode_variable(name: str, info: dict[str, object]) -> None` - Decodes a global variable and registers it in a specification context instance

#### Implementation details

Global variable decoding validates that the initializer value matches the declared type and registers the variable in the specification context's `global_variables` dictionary. The variable decoder uses the same type decoder instance to convert the encoded type info objects back into `TypeInfo` instances.

### `FunctionDecoder: object`

Decodes function information from JSON dictionaries and reconstructs function implementations, registering it as part of a given specification.

#### Public API

- **Fields:**
  - `spec: GlobalContext` - Reference to the specification context where decoded functions are registered
  - `type_decoder: TypeDecoder` - Reference to the type decoder for decoding parameter and return types

- **Methods:**
  - `decode_function(full_name: str, info: dict[str, object], entry_node: Node | None) -> None` - Decodes a function header and implementation, registering it in the specification context

#### Implementation details

Function decoding reconstructs the function's implementation metadata by decoding local variables and attaching the provided CFG entry node. The decoder uses common type info decoder to convert encoded type metadata back into `TypeInfo` objects. Static methods are registered in the structure's `static_methods` dictionary, while instance methods are registered in the structure's `methods` dictionary. The function and its symbols are then registered in the specification context.

### `InstructionDecoder: object`

Decodes individual instructions from JSON dictionaries back into instruction objects. Uses a dispatcher pattern similar to the encoder.

#### Public API

- **Fields:**
  - `type_decoder: TypeDecoder` - Reference to the type decoder for decoding type information in instructions
  - `decoders: dict[str, Callable[[dict[str, object]], Instruction]]` - Mapping from instruction class names to their decoder methods

- **Methods:**
  - `decode_instruction(info: dict[str, object]) -> Instruction` - Decodes an instruction by dispatching to the appropriate decoder method based on the `_` discriminator field

#### Implementation details

The decoder uses a dictionary-based dispatcher (`decoders`) that maps instruction class names to their respective decoder methods. This design allows for easy extension with new instruction types by simply adding a new entry to the dispatcher. Instructions that don't require special handling (like `Pop`, `Assume`, `ExceptionRead`) use a default decoder that uses default constructor with no arguments.

### `CfgDecoder: object`

Decodes control flow graphs from JSON dictionaries back into node-based CFGs. Uses a recursive approach to reconstruct the entire CFG.

#### Public API

- **Fields:** (none)

- **Methods:**
  - `decode_function_body(function_info: dict[str, object], cfg_nodes: dict[str, object]) -> Node | None` - Decodes the implementation body of a function, returning the entry node

#### Implementation details

The decoder uses a linked-list reconstruction strategy that follows the `next` pointer in each node to build the complete CFG. Each node is decoded by dispatching to the appropriate decoder method based on the `_` discriminator field. Control flow nodes (`Switch`, `While`, `TryBlock`) decode their branch targets recursively, using the `cfg_nodes` dictionary as a lookup table. The decoder handles null entries gracefully, allowing for optional branches and termination points.

### `ProgramStateEncoder: object`

Encodes program execution states into JSON-compatible dictionaries.

#### Public API

- **Fields:**
  - `type_encoder: TypeEncoder` - Reference to the type encoder for encoding object types in a unified way

- **Methods:**
  - `encode_object(obj: ObjectState) -> object` - Encodes an object state including type and field values
  - `encode_variable(vs: VariableState) -> object` - Encodes a global variable state

#### Implementation details

Program state encoding `save_state_to_*` preserves the exact structure of the state, including global variables, expected objects, and all object instances. The `ProgramStateEncoder` uses the type encoder to encode object types, ensuring that type information is preserved. The `allow-object-reuse` flag is included in the encoded state to control whether object instances with *1-to-1 matching states* can be reused across different locations.

### `ProgramStateDecoder: object`

Decodes program execution states from JSON dictionaries back into `ProgramState` objects.

#### Public API

- **Fields:**
  - `type_decoder: TypeDecoder` - Reference to the type decoder for decoding object types

- **Methods:**
  - `decode_global_variable(name: str, value: InitializerValueType, info: VariableInfo) -> VariableState` - Decodes a global variable state
  - `decode_object(name: str, info: dict[str, object]) -> ObjectState` - Decodes an object state including type and field values

#### Implementation details

The decoder reconstructs and validates that state values match their declared types, raising `ValueError` for mismatches. For reference types, the decoder accepts either `null`/`0` or a string representing an object ID. For container types (arrays, sets, maps, transforms), the decoder validates that the state is a list and that map/transform states are pairs of values.

## Module-level functions

- `save_context_to_string(ctx: GlobalContext, *, compact: bool = False) -> str` - Serializes a given program specification into a (compact) JSON string. The conversion is done via collective work of a `TypeEncoder`, `GlobalVariableEncoder`, `NodeEnumerator`, `FunctionEncoder`, `InstructionEncoder`, and `CfgEncoder`.

- `save_context_to_file(ctx: GlobalContext, file: object, *, compact: bool = False) -> None` - Serializes a given program specification to a (compact) JSON file. This function works similar to `save_context_to_string()`, but writes the resulting data directly to the file object using `json.dump()`.

- `load_context_from_string(raw_data: str) -> GlobalContext` - Deserializes a program specification from a given JSON string. The reconstruction is done by using `json.loads()` and a collective work of a `TypeDecoder`, `GlobalVariableDecoder`, `FunctionDecoder`, `InstructionDecoder`, and `CfgDecoder`, iterating through the encoded types, global variables, and functions.

- `load_context_from_file(file: object) -> GlobalContext` - Deserializes a program specification from a (given) JSON file. This function works similar to `load_context_from_string()`, but reads the JSON data directly from the file object using `json.load()`.

- `save_state_to_string(state: ProgramState, *, compact: bool = False) -> str` - Serializes a (given) program execution state to a (compact) JSON string. The conversion is done via collective work of a `TypeEncoder` and `ProgramStateEncoder`. The result includes global variables, expected objects, the `allow-object-reuse` flag, and all object instances with their types and states.

- `save_state_to_file(state: ProgramState, file: object, *, compact: bool = False) -> None` - Serializes a (given) program execution state to a (compact) JSON file. This function works similar to `save_state_to_string()`, but writes the serialized data directly to the file object using `json.dump()`.

- `load_state_from_string(ctx: GlobalContext, raw_data: str, *, prune: bool = True) -> ProgramState` - Deserializes a (pruned) program execution state from a (given) JSON string. The reconstruction is done by using `json.loads()` and performing the actual deserialization via a `TypeDecoder` and a `ProgramStateDecoder`, decoding global variables and all objects. If `prune=True`, removes objects that are not reachable from expected objects or global variables.

- `load_state_from_file(ctx: GlobalContext, f: object, *, prune: bool = True) -> ProgramState` - Deserializes a (pruned) program execution state from a (given) JSON file. This function works similar to `load_state_from_string()`, but reads the JSON data directly from the file object using `json.load()`.

---

*AI usage disclosure: this document was generated by a large language model, all text has been validated and edited by a human developer.*
