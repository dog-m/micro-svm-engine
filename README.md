# Micro-SVM

A simple and very basic symbolic virtual machine.

> [!IMPORTANT]
> This is a major piece for an ongoing research project.
> We are currently working hard on preparing our results for a publication.

## Overview

Micro-SVM is a standalone symbolic execution engine designed to:

- Explore program execution paths.
- Analyze control flow and state transitions.
- Validate program specifications against expected behaviors.
- Detect potential defects (e.g., unhandled exceptions, infinite loops).

This package provides the core symbolic execution engine used in research projects for defect discovery and path validation.
It is **not** a full programming language implementation but rather a tool for analyzing executable specifications.

## Supported features

- A range of primitive types: `boolean`, `int8/16/32/64`, `integer`, `real`, `char`, `string`.
- Symbolic primitive values.
- Built-in containers for primitives: `array<T>`, `set<T>`, `map<K,V>`, `transform<K,V>` (same as `map`, more limited but *sometimes* faster).
- Functions and/or static methods.
- Java/C#-like reference values (`ref<T>` for references of known type, plain `ref` for "opaque" cases).
- Structures and "classes" (i.e., structures with methods) with multiple inheritance.
- Handling of abstract methods and virtual calls.
- Intrinsics for specific operations.
- Basic library/program specification serialization (JSON).
- Ability to discover and validate both *normal* and *failing* execution paths (see [examples](examples/defect_detection)).
- Basic class-based user-defined exception handling (i.e. the usual `try-catch-finally` triplet and `throw`).
- Basic decoding of complex structures (containers and structures/classes) as Python objects (i.e. as a list, a list of pairs or a dictionary).

## Installation

```bash
pip install micro-svm
```

## Known limitations

- No function/method overload.
- No type checks. It is expected for a specification to be validated and type-checked by *external tools*.
- Little to no type conversion. The implementation relies heavily on Z3 in that aspect.
- No support for IEEE floats.
- Eager function/method execution. For every discovered program path, the machine checks if the whole path can be executed or not.
  For example, when processing `x = parse_bool(input) or panic()` or similar expression the `panic()` call would **always** be visited unless modelled otherwise in the user specification.
- Very crude fault handling for certain language- and runtime-specific edge-cases. It is only possible to:
  - not allowing any fault to occur during a path's execution (default),
  - check if they *might* have happened (i.e., using `CompilerContext.get_fault_status/clear_fault_status`),
  - ignore faulty operations.
- Exceptions regarding null-dereferencing, invalid array indexing and alike cannot be raised and caught automatically. It is advised to use `CompilerContext.get_fault_status` and `throw` to raise a suitable exception object. Note that `get_fault_status` is unhelpful unless `SymbolicStateMachine.fault_mode` is set to `STORE`.
- No tools for managing dynamic reflection operations (field access by symbolic name strings, method creation, etc.).

## Cite

```text
@software{microsvm2026,
  title={Micro-SVM: A simple symbolic VM in Python and Z3},
  author={Mikhail Onischuck},
  year={2026},
  url={https://github.com/dog-m/micro-svm-engine}
}
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
