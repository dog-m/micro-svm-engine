# svm/exploration.py

## Overview

### Summary

`PathEnumerator` implements a stack-based depth-first search (DFS) algorithm for enumerating all possible execution paths through a program's control flow graph (CFG). It expands control flow constructs (conditionals, loops, try-catch blocks, function calls) into concrete instruction sequences while managing exploration budgets, call stack depth, and exception handling state. The module produces `ProgramPath` objects representing complete paths that can be validated or analyzed for defects.

### Purpose

The `PathEnumerator` class serves as the core path exploration engine for the symbolic virtual machine. Its primary purpose is to systematically traverse all feasible execution paths through a program specification, transforming high-level control flow constructs into linear sequences of primitive instructions. This enables downstream validation and defect detection by providing concrete path candidates that can be executed against the symbolic execution engine.

### Role in the Project

The exploration module sits at the foundation of the symbolic virtual machine's analysis pipeline. It transforms the abstract CFG representation into executable instruction sequences, serving as the bridge between program specification and symbolic execution. This module works closely with `GlobalContext` for program metadata, `TypeHierarchyResolver` for virtual call resolution, and `SymbolicStateMachine` for path validation. The paths produced by this module are consumed by the defect detection system to verify program correctness and generate test cases.

### Contracts

The module expects `Program` objects containing a `GlobalContext` instance and a `CompiledSubroutine` representing the program's entry point. The `TypeHierarchyResolver` must be pre-analyzed and ready to resolve virtual call targets. The module assumes that CFG nodes are properly structured with `BasicBlock` instructions, `Switch` conditionals, `While` loops, `TryBlock` exception handlers, and appropriate `MarkerNode` terminators. The module does not modify the original CFG; all transformations create deep copies.

## Classes

### `Program: object`

A lightweight container for program metadata and entry point information.

#### Public API

- **Fields:**
  - `context: GlobalContext` - Global context containing program-wide information (types, functions, global variables)
  - `main_subroutine: CompiledSubroutine` - The entry subroutine containing the program's entry node

#### Implementation details

`Program` is a simple data container with no behavioral logic. It serves to bundle the global context and entry point into a single object that can be passed to the path enumerator. The `main_subroutine` must contain a valid `entry_node` that serves as the starting point for path exploration.

### `ProgramPath: object`

Represents a complete execution path through the program consisting of a sequence of basic blocks.

#### Public API

- **Fields:**
  - `end_is_reached: bool` - Flag indicating whether the end of the program has been reached
  - `steps: list[BasicBlock]` - Ordered sequence of basic blocks forming the path

- **Methods:**
  - `get_trace(*, prefix='', suffix='') -> str` - Returns a formatted string representation of the entire instruction sequence with optional prefix and suffix
  - `instructions() -> Iterable[Instruction]` - Generator that yields all instructions in the path in order; resets `end_is_reached` to `False` before iteration and sets it to `True` after completion

#### Implementation details

`ProgramPath` provides a simple abstraction for representing complete execution paths. The `instructions()` method is a generator to avoid materializing the entire instruction sequence at once, which is important for memory efficiency when exploring many paths. The `get_trace()` method is primarily used for debugging and logging purposes, producing human-readable output of the path.

### `EnumeratorFailureMetadataTags: object`

Defines metadata tags used to identify different types of failure conditions during path exploration.

#### Public API

- **Fields:**
  - `stack_overflow: str` - Tag identifier for paths that exceed call stack depth limits (default `#stack-overflow`)
  - `unhandled_exception: str` - Tag identifier for paths that encounter unhandled exceptions (default `#unhandled-exception`)

#### Implementation details

These tags are used to categorize failing paths for downstream analysis. The `unhandled_exception` tag is applied when a `Throw` instruction encounters no matching exception handler. The `stack_overflow` tag is applied when the simulated call stack exceeds `call_stack_max_depth` configuration limit, indicating potential infinite recursion.

### `EnumeratorConfig: object`

Configuration parameters controlling path exploration behavior and limits.

#### Public API

- **Fields:**
  - `call_stack_max_depth: int` - Maximum depth of simulated call stack before considering a path as failing (default: 5)
  - `failure_tags: EnumeratorFailureMetadataTags` - Collection of failure metadata tags
  - `loop_max_iter_count: int` - Maximum number of loop iterations at the outermost nesting level (default: 17)
  - `loop_reduction_factor: float` - Exponential reduction factor applied to loop iteration limits per nesting level (default: 10.0)
  - `path_max_count: int` - Maximum number of complete paths to explore before giving up (default: 1024)

- **Methods:**
  - `get_loop_iterations_limit(level: int) -> int` - Returns the maximum iteration count for a loop at the given nesting level, calculated as `loop_max_iter_count / loop_reduction_factor ** level`

#### Implementation details

The loop iteration limits follow an exponential decay strategy: each level of loop nesting reduces the allowed iterations by a factor of `loop_reduction_factor`. This prevents exponential path explosion while still exploring multiple iterations of nested loops. The `get_loop_iterations_limit()` method implements this calculation, ensuring that deeply nested loops have significantly fewer iterations. The `path_max_count` limit prevents unbounded exploration when the program has many feasible paths.

### `ExceptionHandlingTable: object`

Tracks exception handling state for a specific try-catch block during path exploration.

#### Public API

- **Fields:**
  - `boundary: StackBoundary` - Stack boundary marker for exception cleanup
  - `handlers: dict[str, Node]` - Mapping from exception type names to handler nodes
  - `handler_stack_frame_number: int` - Call stack size when the try-block was entered
  - `handler_try_block_number: int` - Index of this try-block in the exception handler stack
  - `loop_level: int` - Loop nesting level when the try-block was entered

#### Implementation details

`ExceptionHandlingTable` maintains the state necessary to properly unwind the execution stack when an exception is thrown. The `handlers` dictionary stores cloned handler nodes with appropriate continuations. The `boundary` marker is pushed onto the execution stack during `TryBlock` entry and popped during `MarkerTryBlockEnd` to manage stack cleanup. The stack frame and loop level information is critical for correctly restoring state when an exception handler is entered or exited.

### `PathEnumerator: object`

Stack-based DFS path enumeration utility that transforms CFG nodes into executable instruction sequences.

#### Public API

- **Fields:**
  - `config: EnumeratorConfig` - Exploration configuration
  - `on_complete_path: Callable[[ProgramPath, 'PathEnumerator'], None] | None` - Callback invoked when a complete path is found
  - `on_failing_path: Callable[[ProgramPath, 'PathEnumerator', str | None, list[str]], None] | None` - Callback invoked when a failing path is found
  - `on_extinguished_path: Callable[['PathEnumerator'], None] | None` - Callback invoked when a path budget is exhausted
  - `program: Program` - Program being explored
  - `session_prefix: str` - Prefix for control point identifiers

- **Methods:**
  - `explore(branching_budget: int = 10) -> None` - Starts path enumeration with the given branching budget
  - `visit_CFG_*(node: <Node subclass>) -> None` - A family of handler methods for visiting and processing a specific type of node in a CFG, typically creating and scheduling separate copies of the current path through a program when dealing with branching point.
  - `stop_exploration() -> None` - Stops the exploration process

#### Implementation details

`PathEnumerator` uses an explicit stack-based DFS algorithm to avoid Python's recursion limits. The `explore()` method initializes the exploration with the main subroutine's entry node and a branching budget, then enters a loop that processes paths from the exploration queue. The `Path` inner class maintains extensive state including the current node, budget, accumulated steps, branch identifiers, loop level, call stack, and exception handler stack.

The core traversal logic is implemented through visitor methods for each CFG node type: `visit_CFG_BasicBlock`, `visit_CFG_While`, `visit_CFG_Switch`, `visit_CFG_CallStatic`, `visit_CFG_CallVirtual`, `visit_CFG_TryBlock`, `visit_CFG_Throw`, `visit_CFG_Break`, `visit_CFG_Continue`, `visit_CFG_FailurePath`, `visit_CFG_EndOfProgram`, and various marker nodes. Each visitor method creates deep copies of CFG nodes and assembles them into linear instruction sequences.

For loops, `visit_CFG_While` unrolls the loop body up to the iteration limit, creating a chain of condition-body-marker iterations followed by a final (negated) condition that leads to the loop exit marker.

Virtual calls are expanded by querying the `TypeHierarchyResolver` for all possible implementations, then creating type guard checks for each candidate. Each guard creates a branch that either proceeds with the call or fails the type check. Static calls are handled similarly but without type guards, simply cloning the implementation and managing the call stack.

Exception handling is complex: `visit_CFG_TryBlock` creates an exception handler table and pushes it onto the path's exception handler stack, while `visit_CFG_Throw` constructs all possible exception handler continuations by traversing the exception handler stack in reverse order, creating type guard expressions for each handler, and scheduling each continuation as a separate path.

### `PathEnumerator.Path: object`

Inner class representing a single path being explored through the program's CFG.

#### Public API

- **Fields:**
  - `next_node: Node` - The next CFG node to visit
  - `budget: int` - Remaining branching budget for this path
  - `steps: list[BasicBlock]` - Accumulated basic blocks forming the path
  - `branch_id_stack: list[str]` - Stack of branch identifiers for control points
  - `loop_level: int` - Current loop nesting level
  - `call_stack: list[str]` - Stack of function names representing the call stack
  - `exception_handler_stack: list[ExceptionHandlingTable]` - Stack of exception handling tables

- **Methods:**
  - `clone() -> 'PathEnumerator.Path'` - Creates a deep copy of this path for parallel exploration
  - `update_loop_level(delta: int) -> None` - Updates the loop level by the specified delta
  - `backup_branch_markers() -> list[str]` - Saves the current branch identifier stack
  - `restore_branch_markers(id_stack: list[str]) -> None` - Restores branch identifiers from the saved stack

#### Implementation details

The `Path` class maintains all state necessary for path exploration, including the current position in the CFG, remaining budget, accumulated path steps, and various context stacks for control flow constructs. The `clone()` method creates independent copies to enable parallel exploration of different branches, while the marker management methods allow for saving and restoring branch context when exploring nested control structures.

## Module-level functions

None.

---

*AI usage disclosure: this document was generated by a large language model, all text has been validated and edited by a human developer.*
