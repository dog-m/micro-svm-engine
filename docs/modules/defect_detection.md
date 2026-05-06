# micro_svm.defect_detection

## Overview

### Summary

The `DefectAnalyzer` class in the `micro_svm.defect_detection` module implements a proof-of-concept defect detection system that identifies potential program failures by exploring all possible execution paths through a program specification (a function/method). It leverages symbolic execution for finding paths that lead to errors (unhandled exceptions, stack overflows, etc.), then optimizes and decodes the resulting program states to produce concrete failure examples. The module employs two reduction tactics - reducing the number of unique object instances and constraining container sizes, - to make otherwise intractable failure states solvable.

### Purpose

The primary purpose of this module is to automatically discover and demonstrate program defects by providing concrete counterexamples that trigger failures. Unlike static analysis that merely identifies potential issues, this module actively explores the program's execution space to find actual failing paths, then reconstructs the exact program state that triggers those failures. This capability enables developers to:

- Verify that specifications correctly handle edge cases and error conditions
- Demonstrate that certain program behaviors are impossible under valid inputs
- Generate test cases that expose specification bugs or implementation errors
- Understand the precise conditions that lead to program failures

The module is designed as a proof-of-concept tool that showcases the symbiotic relationship between path exploration and model decoding—where one component finds problems and the other validates and explains them.

### Role in the Project

No other module depends on the defect detection functionality. This module serves as a primary demonstration of the features and capabilities of other existing modules and systems in the Micro-SVM project.

### Contracts

The `DefectAnalyzer` class makes several assumptions about its dependencies and the program specifications it analyzes:

- **GlobalContext**: The module expects a fully initialized `GlobalContext` instance containing:
  - Complete type hierarchy information (structures, classes, their fields and inheritance relationships)
  - All function specifications with their parameters, return types, and implementation CFGs
  - Global variable declarations and initializers
  - Registered symbols for all variables (parameters, locals, globals)

- **TypeHierarchyResolver**: Requires a properly initialized resolver with the internal representation already pre-built before path exploration begins.

- **Program Specifications**: The analyzed specifications must:
  - Include explicit error handling via `error()` calls in the CFG to mark failing paths
  - Define fault and exception handling with `try-block` and `throw` nodes

- **Callback Interface**: The module supports an optional callback mechanism via the `on_defect` property that accepts a `DetectedFailure` instance, allowing external code to handle discovered defects.

## Classes

### `DefectAnalyzer: object`

The `DefectAnalyzer` class is the central component of the defect detection system. It orchestrates the entire defect detection workflow, from path exploration to state optimization and failure reporting.

#### Public API

- **Fields:**
  - `config: DefectAnalyzerConfig` - Configuration object containing analysis parameters
  - `defects_found: int` - Counter tracking the total number of defects discovered during analysis
  - `on_defect: Callable[[DetectedFailure], None] | None` - Optional callback function invoked when a defect is found
  - `th_resolver: TypeHierarchyResolver` - Resolver for type hierarchy relationships and virtual method dispatch
  - `size_type: TypeInfo` - Type information for integer types used for container size operations
  - `spec: GlobalContext` - The global context containing the complete program specification (types, functions, global variables)

- **Methods:**
  - `analyze_function(function_name: str) -> None` - Analyzes a single function for defects by exploring all execution paths, executing them symbolically, and reporting any failures found

#### Implementation details

The `analyze_function` method implements a multi-stage analysis pipeline:

1. Creates a symbolic program that includes a call to the target function, assuming symbolic values for all parameters and registering local variables with special tags for solution tracking.
2. Explores all possible execution paths through the compiled program, collecting paths that lead to `error()` calls or other failure termination points. The exploration respects the `loop_max_iter_count`, `loop_reduction_factor`, and `branching_budget` configuration parameters (see `DefectAnalyzerConfig`).
3. For each failing path, creates a `SymbolicStateMachine` instance and executes the path instructions to verify the path is actually executable.
4. State Optimization: applies reduction tactics to simplify the program state before decoding:
   - **Object Count Reduction**: Reduces the number of unique object instances by asserting that fewer distinct references exist than currently present
   - **Collection Size Reduction**: Constrains container sizes to reduce the state space, particularly effective for handling large collections
5. Uses `StateIntermediateDescription.analyze()` to decode the optimized symbolic state into a structured representation with reachability information and object relationships.
6. Converts the decoded state into a `DetectedFailure` instance with concrete argument values and program state, including all objects referenced by the failing call.

The optimization process is iterative - when a reduction tactic succeeds in finding a feasible solution, the state is re-analyzed with the simplified constraints. This continues until no further reductions are possible.

### `DefectAnalyzerConfig: object`

This class encapsulates all configurable parameters for defect detection analysis.

#### Public API

- **Fields:**
  - `branching_budget: int` - Maximum number of branches to explore (default: `10`). Controls exploration breadth
  - `loop_max_iter_count: int` - Maximum number of loop iterations to explore (default: `17`). Limits path explosion in loops
  - `loop_reduction_factor: float` - Factor for reducing loop iteration counts during exploration (default: `10.0`). Helps manage state space
  - `max_collection_size: int` - Maximum allowed size for any container (default: `50`). Used to constrain collection growth during state optimization
  - `solver_try_count: int` - Number of solver attempts for each constraint (default: `21`). Controls solver robustness
  - `timeout: float` - Solver timeout in milliseconds (default: `2100` ms). Applied to each symbolic execution attempt

### `DetectedFailure: object`

This class represents a discovered defect with all relevant information for reporting and analysis.

#### Public API

- **Fields:**
  - `call_args: list[ValueType]` - List of concrete argument values passed to the failing function (note: non-null references are represented as object string identifiers)
  - `failure_id: Any` - Identifier for this specific failure (e.g., "#stack-overflow")
  - `function_name: str` - Name of the function/method where the failure occurred
  - `program_state: ProgramState` - Complete program state including global variables and all objects

- **Methods:**
  - `as_string(ctx: GlobalContext) -> str` - Returns a human-readable string representation of the failure, including function name and formatted arguments

#### Implementation details

The `as_string` method formats the failure in a way that can be used as a test case or example. For static functions, it produces output like `std.List.makeFrom(#000)`, while for instance methods it produces `#000.equals(#000)`. The method uses the `GlobalContext.functions` mapping to access parameter type information for proper argument formatting.

### `RefIdGenerator: object`

The `RefIdGenerator` class generates unique string identifiers for object references during state refinement.

#### Public API

- **Methods:**
  - `get(ref: int) -> str | None` - Returns a string ID for the given reference, generating a new one if necessary. Returns `None` for reference value `0` (null)

#### Implementation details

The generator uses hexadecimal encoding with zero-padding (e.g., `#000`, `#001`) to create human-readable object identifiers. This can be useful for debugging and presenting failure states in logs.

### `ReferenceHandlePool: object`

The `ReferenceHandlePool` class manages the creation of symbolic variable handles for grounding references during state optimization.

#### Public API

- **Fields:**
  - `ctx: GlobalContext` - Global context for registering symbols
  - `items: list[VariableInfo]` - Pool of available variable handles
  - `last: int` - Index of the most recently created handle

- **Methods:**
  - `get() -> VariableInfo` - Returns a new variable handle, creating it if necessary
  - `reset() -> None` - Resets the pool to allow reuse of handles

#### Implementation details

The pool maintains a list of `VariableInfo` objects representing symbolic variables. Each handle is registered with the global context and can be used to create symbolic expressions for reference grounding. The `reset()` method is called between optimization attempts to allow reuse of the same pool.

## Module-level functions

None.

---

*AI usage disclosure: this document was generated by a large language model, all text has been validated and edited by a human developer.*
