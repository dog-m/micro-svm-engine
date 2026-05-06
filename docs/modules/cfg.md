# micro_svm.cfg

## Overview

### Summary

The module `micro_svm.cfg` defines the Control Flow Graph (CFG) node hierarchy used throughout the symbolic virtual machine for representing program control flow in specifications. This module provides a tree-like structure where `BasicBlock` nodes contain executable instructions, while special control flow nodes like `Switch`, `While`, `TryBlock`, `CallStatic`, and `CallVirtual` represent branching, loops, exception handling, and subroutine calls. The module also includes `CFGNodeResolver` for traversing and visiting CFG nodes, and `ProgramVisualiser` for rendering control flow graphs in a human-readable format.

### Purpose

The primary purpose of this module is to provide a structured representation of program control flow that can be dynamically expanded during path exploration. Unlike traditional CFG implementations that are static and immutable, this module's nodes are designed to be cloned and modified during symbolic execution to generate all possible execution paths through a program. Each node type serves a specific purpose in representing different control flow constructs, from simple sequential execution in `BasicBlock` to complex exception handling in `TryBlock`. The module ensures that the original specification remains unchanged while allowing for safe, isolated exploration of alternative execution paths.

### Role in the Project

The module serves as the data structure layer for the symbolic virtual machine's path enumeration system, providing the graph-based representation that is traversed and expanded by `micro_svm.exploration`. The CFG nodes are serialized to JSON format (see `micro_svm.serialization`) and loaded back for program execution or analysis, enabling persistent storage and sharing of program specifications. This module works closely with `micro_svm.instructions` to represent executable code, and with `micro_svm.global_context` to access function and structure metadata during node creation and traversal.

### Contracts

The module assumes that all node types are immutable after creation, with cloning performed via `clone_self()` and `clone()` methods. The `CFGNodeResolver` expects the visitor object to implement specific `visit_CFG_<ClassName>` methods for each node type, or provide a default handler. The `ProgramVisualiser` assumes that instruction objects implement `__str__()` methods that produce human-readable output suitable for display.

## Classes

### `Node: ABC`

Abstract base class for all CFG nodes providing common functionality for linked-list-like structure traversal and cloning.

#### Public API

- **Fields:**
  - `next: Node | None` - The next node in the linked structure sequence; can be `None` indicating the end of a chain

- **Methods:**
  - `has_next() -> bool` - Returns `True` if a node has a successor
  - `get_last() -> Node` - Traverses the linked list starting from the current node and returns the final node in the chain
  - `clone_self(dup_instructions: bool = False) -> Node` - Abstract method that must be implemented by subclasses to create a deep copy of the **node's internal state**; `dup_instructions` controls whether instruction lists should be copied or shared
  - `clone(dup_instructions: bool = False) -> Node` - Creates a deep copy of the entire node **chain** starting from this node, including all subsequent nodes in the linked list

#### Implementation details

The `Node` class implements a simple singly-linked list structure where each node can have a reference to its successor. This design enables efficient traversal of control flow chains while supporting deep copying for path exploration. The `clone()` method recursively clones the entire chain, ensuring that modifications to one path do not affect other paths. The `get_last()` method performs an iterative traversal to find the terminal node, which is useful for appending new nodes to existing chains.

### `MarkerNode: Node, ABC`

Abstract base class for marker nodes that signal specific execution points.

#### Public API

- **Fields:**
  - Inherits all fields from `Node`

- **Methods:**
  - Inherits all methods from `Node`

#### Implementation details

Marker nodes serve as terminators in control flow graphs, indicating special points such as program end, failure conditions, or loop iteration boundaries. They are designed to be immutable and non-extendable during path exploration, preventing infinite loops or unbounded path generation. The `MarkerNode` class provides a common base for all such special-purpose nodes in the system.

### `BasicBlock: Node`

A sequence of executable instructions representing a basic block of code.

#### Public API

- **Fields:**
  - Inherits all fields from `Node`
  - `instructions: list[Instruction]` - A list of `Instruction` objects that will be executed sequentially

- **Methods:**
  - Inherits all methods from `Node`
  - `clone_self(dup_instructions: bool = False) -> BasicBlock` - Creates a copy of this basic block; if `dup_instructions` is `True`, a deep copy of the instruction list is made; otherwise, the original instruction list is shared between the clone and the original

#### Implementation details

`BasicBlock` nodes are the primary containers for executable code in the symbolic virtual machine. During path exploration, these blocks are dynamically stitched together to form complete execution paths. The `clone_self()` method provides flexibility in whether instruction lists should be shared or duplicated, which is important for memory efficiency when exploring many similar paths. Basic blocks are typically used for sequential execution and represent the atomic unit of code that can be executed without branching.

### `FailurePath: MarkerNode`

A marker node that terminates a path and marks it as a failing candidate.

#### Public API

- **Fields:**
  - `metadata: str | None` - Optional metadata describing the failure condition or context

- **Methods:**
  - Inherits all methods from `MarkerNode`
  - `__str__() -> str` - Returns a string representation in the format `<marker: failure> [metadata=...]`
  - `clone_self(dup_instructions: bool = False) -> FailurePath` - Creates a new `FailurePath` instance with the same metadata

#### Implementation details

`FailurePath` nodes signal that a particular execution path leads to an expected error condition, such as an unhandled exception or a failure assertion. The optional `metadata` field provides context about why the path failed, which can be useful for debugging and defect detection. During path exploration, encountering a `FailurePath` node terminates that particular path without further exploration, as it represents a known failure scenario rather than a valid execution sequence.

### `EndOfProgram: MarkerNode`

A marker node that terminates a path and marks it as a normal (successful) candidate.

#### Public API

- **Fields:**
  - Inherits all fields from `MarkerNode`

- **Methods:**
  - Inherits all methods from `MarkerNode`
  - `__str__() -> str` - Returns the string representation `<marker: end-of-program>`
  - `clone_self(dup_instructions: bool = False) -> EndOfProgram` - Creates a new `EndOfProgram` instance

#### Implementation details

`EndOfProgram` nodes mark the successful completion of the entire program. When encountered during path exploration, this signals that the current path should be considered valid and reaches a terminal state. Unlike `FailurePath` nodes, `EndOfProgram` nodes represent successful execution.

### `CallStatic: Node`

Represents a static function call where arguments are automatically pulled from the top of the execution stack.

#### Public API

- **Fields:**
  - `function_name: str` - The name of the static function to call
  - `argument_count: int` - The number of arguments that will be consumed from the stack

- **Methods:**
  - Inherits all methods from `Node`
  - `__str__() -> str` - Returns a string representation in the format `<call-static> [func={function_name}, argc={argument_count}]`
  - `clone_self(dup_instructions: bool = False) -> CallStatic` - Creates a new `CallStatic` instance with the same function name and argument count

#### Implementation details

`CallStatic` nodes represent calls to static functions or methods. During path exploration, these nodes are expanded by replacing themselves with the implementation of the called function, effectively inlining the subroutine call. The `argument_count` field specifies how many arguments will be consumed from the execution stack, which is determined by the function's signature. This node type is critical for handling procedural code and enabling the symbolic virtual machine to execute user-defined functions.

### `CallVirtual: Node`

Represents a virtual method call where arguments are automatically pulled from the top of the execution stack.

#### Public API

- **Fields:**
  - `structure_name: str` - The name of the structure/class containing the method
  - `method_name: str` - The name of the virtual method to call
  - `argument_count: int` - The number of arguments that will be consumed from the stack

- **Methods:**
  - Inherits all methods from `Node`
  - `__str__() -> str` - Returns a string representation in the format `<call-virtual> [func={structure_name}.{method_name}, argc={argument_count}]`
  - `clone_self(dup_instructions: bool = False) -> CallVirtual` - Creates a new `CallVirtual` instance with the same structure name, method name, and argument count

#### Implementation details

`CallVirtual` nodes represent calls to virtual methods, which require dynamic dispatch based on the actual type of the object instance. During path exploration, these nodes are expanded by resolving the method to its concrete implementation(s) using the `TypeHierarchyResolver` class. Each resolved implementation is then treated as a separate `CallStatic` node, enabling the exploration of different method implementations based on the object's type hierarchy. This dynamic dispatch mechanism is essential for supporting object-oriented programming features in the symbolic virtual machine.

### `MarkerFunctionExit: MarkerNode`

A marker node that signals the end of a subroutine call.

#### Public API

- **Fields:**
  - Inherits all fields from `MarkerNode`

- **Methods:**
  - Inherits all methods from `MarkerNode`
  - `__str__() -> str` - Returns the string representation `<marker: function-exit>`
  - `clone_self(dup_instructions: bool = False) -> MarkerFunctionExit` - Creates a new `MarkerFunctionExit` instance

#### Implementation details

`MarkerFunctionExit` nodes mark the point where a subroutine call returns control to its caller. These nodes are typically attached to the last node of a function's implementation and are used to manage the call stack during path exploration. They ensure proper stack frame management and help maintain the correct context when returning from subroutine calls.

### `While: Node`

A branching node representing a while loop construct.

#### Public API

- **Fields:**
  - `loop_id: int | str` - A unique identifier for the loop, used for break and continue operations
  - `condition: Node` - The condition node that determines whether to continue iterating
  - `body: Node` - The node to execute in each iteration of the loop

- **Methods:**
  - Inherits all methods from `Node`
  - `clone_self(dup_instructions: bool = False) -> While` - Creates a new `While` node with cloned condition and body nodes

#### Implementation details

`While` nodes implement while-loops in the control flow graph. The `loop_id` field provides a unique identifier for the loop, which is used by `Break` and `Continue` nodes to target specific loops. During path exploration, while-loops are handled with iteration limits to prevent exponential path explosion (see `micro_svm.exploration` for details on `loop_max_iter_count` and `loop_reduction_factor`). The loop body is cloned and attached to the loop condition to create multiple iterations of the loop.

### `MarkerLoopEnd: MarkerNode`

A marker node that signals the end of a single iteration in a loop.

#### Public API

- **Fields:**
  - `loop_id: int | str` - The identifier of the loop this marker belongs to

- **Methods:**
  - Inherits all methods from `MarkerNode`
  - `__str__() -> str` - Returns a string representation in the format `<marker: loop-end> [loop=#{loop_id}]`
  - `clone_self(dup_instructions: bool = False) -> MarkerLoopEnd` - Creates a new `MarkerLoopEnd` instance with the same loop identifier

#### Implementation details

`MarkerLoopEnd` nodes mark the end of each iteration in a loop, typically placed after the loop body. These nodes are used to manage loop iteration and can be targeted by `Break` and `Continue` nodes. They help maintain the correct control flow structure during path exploration and ensure that loop iterations are properly bounded.

### `MarkerLoopIterationEnd: MarkerNode`

A marker node that signals the end of a single iteration in a loop, providing additional iteration control.

#### Public API

- **Fields:**
  - `loop_id: int | str` - The identifier of the loop this marker belongs to

- **Methods:**
  - Inherits all methods from `MarkerNode`
  - `__str__() -> str` - Returns a string representation in the format `<marker: loop-iter-end> [loop=#{loop_id}]`
  - `clone_self(dup_instructions: bool = False) -> MarkerLoopIterationEnd` - Creates a new `MarkerLoopIterationEnd` instance with the same loop identifier

#### Implementation details

`MarkerLoopIterationEnd` serves a similar purpose to `MarkerLoopEnd` but provides an additional marker point for loop iteration management. This distinction allows for more granular control over loop iteration during path exploration, particularly when dealing with complex loop structures that require multiple exit points.

### `Break: Node`

Represents a break instruction for terminating a loop during path exploration.

#### Public API

- **Fields:**
  - `loop_id: int | str` - The identifier of the loop to break from

- **Methods:**
  - Inherits all methods from `Node`
  - `__str__() -> str` - Returns a string representation in the format `<break> [loop=#{loop_id}]`
  - `clone_self(dup_instructions: bool = False) -> Break` - Creates a new `Break` instance with the same loop identifier

#### Implementation details

`Break` nodes represent the `break` statement in programming languages, which terminates the nearest enclosing loop. During path exploration, encountering a `Break` node causes the current loop iteration to terminate and control flow to continue after the loop body. The `loop_id` field ensures that the break targets the correct loop, even when dealing with nested loops.

### `Continue: Node`

Represents a continue instruction for skipping to the next iteration of a loop during path exploration.

#### Public API

- **Fields:**
  - `loop_id: int | str` - The identifier of the loop to continue

- **Methods:**
  - Inherits all methods from `Node`
  - `__str__() -> str` - Returns a string representation in the format `<continue> [loop=#{loop_id}]`
  - `clone_self(dup_instructions: bool = False) -> Continue` - Creates a new `Continue` instance with the same loop identifier

#### Implementation details

`Continue` nodes represent the `continue` statement in programming languages, which skips the remainder of the current loop iteration and proceeds to the next iteration. During path exploration, encountering a `Continue` node causes the loop to restart with the next iteration, based on the loop condition. Like `Break` nodes, the `loop_id` field ensures correct targeting of nested loops.

### `TryBlock: Node`

Represents a try-catch-finally block for exception handling.

#### Public API

- **Fields:**
  - `body: Node` - The node representing the code to be executed within the try block
  - `catch_handlers: dict[str, Node]` - A dictionary mapping exception structure names to their handler nodes
  - `finishing_section: Node | None` - The node representing the finally block (optional)

- **Methods:**
  - Inherits all methods from `Node`
  - `clone_self(dup_instructions: bool = False) -> TryBlock` - Creates a new `TryBlock` node with cloned body and handlers

#### Implementation details

`TryBlock` nodes implement exception handling in the symbolic virtual machine. The `body` contains the code that may raise exceptions, `catch_handlers` maps exception types to their handler code, and `finishing_section` represents the finally block that executes regardless of whether an exception occurred. During path exploration, exception handling is managed using an exception handling stack (see `micro_svm.exploration` for details). When a `Throw` node is encountered, the system searches for a matching exception handler and creates a new path continuation that includes the handler's implementation.

### `MarkerTryBlockEnd: MarkerNode`

A marker node that signals the end of a guarded body in a try-block.

#### Public API

- **Fields:**
  - Inherits all fields from `MarkerNode`

- **Methods:**
  - Inherits all methods from `MarkerNode`
  - `__str__() -> str` - Returns the string representation `<marker: try-end>`
  - `clone_self(dup_instructions: bool = False) -> MarkerTryBlockEnd` - Creates a new `MarkerTryBlockEnd` instance

#### Implementation details

`MarkerTryBlockEnd` nodes mark the end of the try block's guarded body, typically placed after the body. These nodes help manage the *boundary* between the try block and the rest of the code, ensuring proper exception handling semantics during path exploration.

### `Switch: Node`

A flexible control flow switching node that evaluates a value and dispatches to different handlers based on conditions.

#### Public API

- **Fields:**
  - `value_source: Node | None` - The node representing the value to be evaluated
  - `cumulative: bool` - A flag indicating whether case handlers should be cumulative (default `False`)
  - `cases: list[tuple[Node, Node]]` - A list of tuples where each tuple contains a condition node and its corresponding handler node

- **Methods:**
  - Inherits all methods from `Node`
  - `clone_self(dup_instructions: bool = False) -> Switch` - Creates a new `Switch` node with cloned value source and cases

#### Implementation details

`Switch` nodes implement flexible control flow switching similar to switch-case statements in programming languages. The `value_source` field contains the node that produces the value to be evaluated, while `cases` contains pairs of condition and handler nodes. When `cumulative` is `True`, handlers are evaluated cumulatively, meaning that if a condition matches, conditions for previous cases would also be evaluated. Otherwise, only a single condition check is dispatched for every program path produced. This is useful for implementing order-dependent statements (eg., type matchers).

### `Throw: Node`

Represents an exception throw operation for exploring exception propagation.

#### Public API

- **Fields:**
  - Inherits all fields from `Node`

- **Methods:**
  - Inherits all methods from `Node`
  - `__str__() -> str` - Returns the string representation `<throw-exception>`
  - `clone_self(dup_instructions: bool = False) -> Throw` - Creates a new `Throw` instance

#### Implementation details

`Throw` nodes represent the throwing of an exception in the program. During path exploration, encountering a `Throw` node triggers exception handling logic, which systematically explores each path going through all catch handlers covering the current point in the program. Every handler is paired with matching exception type guard, and a new path continuation is created that includes the handler's implementation. In cases when there are no active wildcard handlers (such as for `finally` section), a `FailurePath` node is generated to represent an unhandled exception. This mechanism enables the exploration of all possible exception propagation paths through the program.

### `CFGNodeResolver: object`

A visitor pattern implementation for traversing and visiting CFG nodes.

#### Public API

- **Fields:**
  - `visitor: object` - The visitor object that will receive callbacks for each node type
  - `default_handler: Callable[[Node], Any] | None` - A default handler function to use if no specific visitor method is found for a node type (default `None`)

- **Methods:**
  - `visit(node: Node) -> Any` - Visits a single node by calling the appropriate `visit_CFG_<ClassName>` method on the visitor; if no such method exists and a default handler is provided, calls the default handler; otherwise raises an `AssertionError`
  - `visit_chain(starting_node: Node | None) -> Any` - Traverses the linked list starting from `starting_node`, visiting each node in sequence and returning the result of the last visit

#### Implementation details

`CFGNodeResolver` implements the visitor pattern to enable flexible traversal of CFG nodes. The visitor object must implement specific methods for each node type (e.g., `visit_CFG_BasicBlock`, `visit_CFG_While`), or provide a default handler for unknown node types. The `visit_chain()` method performs iterative traversal of linked node chains, which is useful for processing sequences of nodes like basic blocks or loop bodies. This design allows for clean separation of traversal logic from node-specific processing.

### `ProgramVisualiser: object`

A utility class for rendering CFG nodes in a human-readable format.

#### Public API

- **Fields:**
  - `TAB: str` - A constant string of spaces used for indentation (4 spaces by default)
  - `indent: int` - Current indentation level for rendering
  - `resolver: CFGNodeResolver` - A `CFGNodeResolver` configured to use this visualiser as the visitor
  - `printer: Callable[[str], None]` - A callable used for output (defaults to `print`)

- **Methods:**
  - `simple(value: object) -> None` - Prints the value at the current indentation level
  - `update_indentation(delta: int) -> None` - Updates the current indentation level by `delta` spaces, ensuring it remains non-negative
  - `show(title: str, branch: Node | None) -> None` - Displays a title followed by the rendered CFG chain starting from `branch`, with appropriate indentation
  - `visit_CFG_*(node: Node) -> None` - A set of dedicated render handlers for certain types of nodes that require specific output format

#### Implementation details

`ProgramVisualiser` provides a simple but effective way to inspect and debug CFG structures. It uses **recursion** to create a hierarchical view of the control flow graph, making it easier to understand complex branching and nesting. The visualiser is particularly useful during development and testing of program specifications, as it can quickly reveal structural issues or unexpected control flow patterns. The `show()` method is the primary entry point for rendering, which delegates to the appropriate visitor method based on the node type.

## Module-level functions

None.

---

*AI usage disclosure: this document was generated by a large language model, all text has been validated and edited by a human developer.*
