# Micro-SVM

## Specification format

Since the main idea was to use sequences of some "basic" instructions, a *somewhat comprehensive* set of symbolic operations was established (see `micro_svm.instructions`).
This includes not only primitive operations (like pushing values onto the *value stack*, making assumptions/assertions, reading from and writing into variables) but also highly complex ones (like comparing array segments, adding new entries into mappings, accessing object fields) and special "ad-hoc" mechanisms (like error checking, *stack* manipulation, type-specific operations).

A library/program specification consists of *functions* that may have Control-Flow-Graph-like (or more *tree-like*) node-based implementations (see `micro_svm.cfg`).
"Executable" instructions are situated in `BasicBlock`-type of nodes that are just plain lists of instructions that are stitched together dynamically during path exploration phase.
This includes structures like `Switch`-statements, `While`-loops, `TryBlock` nodes, but also `CallStatic` and `CallVirtual` special nodes that are kept separate for clarity (see "node expansion" below).

A typical specification (or a self-contained separate part of it) is handled via `GlobalContext` instance (see `micro_svm.global_context`, there is also a global shared instance called just `CONTEXT`).
This object contains information about each *function* (name, binding, parameters, tags, etc.) and *structure* (name, fields, hierarchy, see `micro_svm.descriptors`).

### Programmatic specification assembly

A simple "compiler" class was created (see `CompilerContext` in `micro_svm.compiler`) for easier creation of user-defined specifications.
This allows using the Python API for modelling program semantics in a somewhat user-friendly way, providing access to a wide variety of intrinsics.
The `CompilerContext` class wraps every operation with a `Readable` object that gathers consecutive instructions and uses *dunder methods* for basic operations (like `__add__` for `+` and so on).
The `VariableHandle` objects are used for doing *writes* on basic variables.
A pair of *read* and *write* handles are joined together inside of a `JoinedHandle` object.

Here is how a basic example of an `std.List.AddLast(value: std.Object)` method looks like (note that `spec` is a `GlobalContext` reference):

```py
def List_AddLast(ctx: CompilerContext):
    this  = ctx.get_parameter('this')
    value = ctx.get_parameter('value')
    items = ctx.make_local_variable(reference)
    count = ctx.make_local_variable(integer)
    # ===
    ctx.write(items.w, ctx.field_read(this.r, 'std.List', 'items'))
    ctx.write(count.w, ctx.container_size(items.r))
    ctx.array_set(reference, items.r, count.r, value.r)
    ctx.array_set_size(reference, items.r, count.r + ctx.const(1))

spec.register_function(
    name='AddLast',
    parameters=[
        ('this', ref(spec.structures['std.List'])),
        ('value', ref(spec.structures['std.Object'])),
    ],
    result=None,
    implementation=List_AddLast,
    structure='std.List',
    tags={ 'public', },
)
```

In this example there are:

- two local variables (`items: ref` and `count: integer`),
- two parameters (`this: ref<std.List>` and `value: ref<std.Object>`),
- reads from variables (like `items.r` and `count.r`), parameters (`this.r`, `value.r`) and fields (`ctx.field_read`),
- usage of high-level intrinsic operations (container element access and size update),
- variable updates/writes (`ctx.write(items.w, ...)`),
- usage of primitive Python constants (`ctx.const(1)` with `type=integer` by default).

Using `CompilerContext` greatly helps with managing cross-procedural interactions such as making calls and passing arguments.
The current design is centered around the "single-entry, single-exit" subroutine structure for simplifying specification assembly and traversal.
One *notable exception* to this rule is using `error(str|None)` to specifically state that this branch cannot be extended further and is indicative of an expected error at this point in the specification (i.e., a failing path would be produced when doing path enumeration through this point).

There are also helper functions `simple_program` and `register_empty_constructor` (see `micro_svm.utils`) that can be used to simplify the process of registering a *main/entry* function of the program (produces `CompiledSubroutine` instance) and creating a basic constructor implementation (thou with some considerations).
This functionality is mainly used for tests.

### Saving and Loading

A simple **JSON-based** structured format is used for describing, storing, and loading both program/library specifications and desired target objects' and global variables' states (see `micro_svm.serialization`).

#### State description

There are a number of fields that are used to describe a program's state (see `micro_svm.state`):

- `global-variables` - a dictionary object where variable name is the key and value is that global variable's value.
It's important to note that for `ref` types, values are either `null`/`0` or a string representing an object ID.
- `expected-objects` - this is a list of IDs of **top-level** objects that are expected to be reconstructed.
If the object is expected to be associated with a global variable, then its ID should **only** be mentioned in the `global-variables` mapping and **not** in the `expected-objects` (as per the original plan).
Think of it as a collection (tuple) of objects expected to be produced by a static function.
- `allow-object-reuse` - this parameter controls whether an object instance *could* be used in multiple places such that the overall state remains *essentially* the same as requested (`true` by default).
- `all-objects` - a flat collection of all object instances and their corresponding states.
This includes field values (`state`) for all fields, including inherited ones as well as the type information object (`type`).

A simple example state description for the above-mentioned `map<integer, integer>` case:

```json
{
    "global-variables": {
        "base_map": "#000"
    },
    "expected-objects": [],
    "all-objects": {
        "#000": {
            "type": { "_": "map", "key": { "_": "integer" }, "value": { "_": "integer" } },
            "state": [
                [0, 0],
                [1, 1],
                [2, 1],
                [3, 2],
                [4, 3]
            ]
        }
    }
}
```

#### Library specification

There are a number of fields that make up an executable specification for this project:

- `types` - describes user-defined structures and classes.
This includes fields (name, type and string tags) and parent structures/classes.
- `global-variables` - describes variables that are accessible globally.
This includes name, type, string tags and an initial `initializer` value.
One notable difference from the state description format is that the `initializer` value can only be a boolean, a number, a string, a list, a list of pairs or a dictionary.
So, currently this restricts the specifications from using pre-initialized inter-dependent objects and structures.
One possible workaround could be using some sort of `pre_main()` static global function that asserts properties of globally-accessible objects and their pieces via local variables.
- `functions` - describes all functions, procedures and methods.
Also, local variables are declared here as they are not accessible outside of their respective functions.
- `cfg-nodes` - is a flat collection of all CFG nodes that are the implementation of the functions described above.
Every node can be accessed via its unique ID and closely matches its underlying data structure and declaration in the `micro_svm.cfg`.

A synthetic example of a specification that declares a `std.Integer` *class*, a global variable `base_map`, and a function `map_get` looks like this:

<details>
<summary>Click here to see an example spec snippet.</summary>

```json
{
    "types": [
        {
            "_": "structure",
            "name": "std.Integer",
            "parents": [ "std.Object" ],
            "fields": {
                "value": { "type": { "_": "integer" }, "tags": [] }
            }
        }
    ],
    "global-variables": {
        "base_map": {
            "type": { "_": "ref", "item": { "_": "map", "key": { "_": "integer" }, "value": { "_": "integer" } } },
            "initializer": {},
            "tags": []
        }
    },
    "functions": {
        "map_get": {
            "original-name": "map_get",
            "structure": null,
            "parameters": [
                { "name": "key", "type": { "_": "integer" } }
            ],
            "result-type": { "_": "integer" },
            "static": true,
            "tags": [],
            "implementation": { "entry": "#0002", "local-variables": [] }
        },
        ...
    },
    "cfg-nodes": {
        ...,
        "#0002": {
            "_": "BasicBlock",
            "instructions": [
                {
                    "_": "SubroutineEnter"
                },
                {
                    "_": "VariableWrite",
                    "destination-name": "map_get#key",
                    "destination-is-local": true
                }
            ],
            "next": "#0003"
        },
        "#0003": {
            "_": "BasicBlock",
            "instructions": [],
            "next": "#0004"
        },
        "#0005": {
            "_": "BasicBlock",
            "instructions": [
                {
                    "_": "VariableRead",
                    "source-name": "base_map",
                    "source-is-local": false
                },
                {
                    "_": "VariableRead",
                    "source-name": "map_get#key",
                    "source-is-local": true
                },
                {
                    "_": "MapOperation",
                    "operation": "HAS_KEY",
                    "key-type": { "_": "integer" },
                    "value-type": { "_": "integer" }
                }
            ],
            "next": null
        },
        "#0006": {
            "_": "BasicBlock",
            "instructions": [
                {
                    "_": "VariableRead",
                    "source-name": "base_map",
                    "source-is-local": false
                },
                {
                    "_": "VariableRead",
                    "source-name": "map_get#key",
                    "source-is-local": true
                },
                {
                    "_": "MapOperation",
                    "operation": "GET",
                    "key-type": { "_": "integer" },
                    "value-type": { "_": "integer" }
                },
                {
                    "_": "VariableWrite",
                    "destination-name": "map_get#~result",
                    "destination-is-local": true
                }
            ],
            "next": null
        },
        "#0006": {
            "_": "BasicBlock",
            "instructions": [],
            "next": null
        },
        "#0007": {
            "_": "BasicBlock",
            "instructions": [
                {
                    "_": "VariableRead",
                    "source-name": "base_map",
                    "source-is-local": false
                },
                {
                    "_": "VariableRead",
                    "source-name": "map_get#key",
                    "source-is-local": true
                },
                {
                    "_": "MapOperation",
                    "operation": "GET",
                    "key-type": { "_": "integer" },
                    "value-type": { "_": "integer" }
                },
                {
                    "_": "VariableWrite",
                    "destination-name": "map_get#~result",
                    "destination-is-local": true
                }
            ],
            "next": null
        },
        "#0008": {
            "_": "BasicBlock",
            "instructions": [
                {
                    "_": "PrimitiveOp",
                    "operation": "NOT"
                }
            ],
            "next": null
        },
        "#0009": {
            "_": "BasicBlock",
            "instructions": [],
            "next": "#000a"
        },
        "#000a": {
            "_": "FailurePath",
            "metadata": null,
            "next": null
        },
        "#0004": {
            "_": "Switch",
            "value_source": "#0005",
            "cumulative": false,
            "cases": {
                "#0006": "#0007",
                "#0008": "#0009"
            },
            "next": "#000b"
        },
        "#000b": {
            "_": "BasicBlock",
            "instructions": [
                {
                    "_": "VariableRead",
                    "source-name": "map_get#~result",
                    "source-is-local": true
                },
                {
                    "_": "SubroutineExit"
                }
            ],
            "next": null
        },
        ...
    }
}
```

</details>

When loaded in, the instruction-level print-out of the function `map_get` would look like this (`<marker: failure>` is a `FailurePath` terminator node):

```text
[static] map_get (key: integer) -> integer:
    SubroutineEnter
    VariableWrite [dst=map_get#key (local)]
    switch [cumulative=False]:
        VariableRead [src=base_map (global)]
        VariableRead [src=map_get#key (local)]
        MapOperation [op=HAS_KEY, type=integer:integer]
        case #0:
            condition:
            handler:
                VariableRead [src=base_map (global)]
                VariableRead [src=map_get#key (local)]
                MapOperation [op=GET, type=integer:integer]
                VariableWrite [dst=map_get#~result (local)]
        case #1:
            condition:
                PrimitiveOp [op=NOT, inputs=1]
            handler:
                <marker: failure [metadata: None]>
    VariableRead [src=map_get#~result (local)]
    SubroutineExit
```

## Symbolic Virtual Machine

This was the first thing that has been created.
There are three parts to this one:

- exploring every path (or as many as we can) through the given program,
- taking each path and making it into a sequence of primitive steps (instructions),
- "executing" these instructions to see if current sequence (and by extension the whole path) can be executed.

### Program path enumeration (exploration and sequencing)

The main approach to generating every path through a given program was/is to use DFS (with a stack to avoid recursion restrictions, see `micro_svm.exploration`), joining each branching segment into a single chain of basic blocks of instructions.
In order to avoid mutating the original CFG, a deep copy of every encountered branch is made with the introduction of additional basic blocks that join and adjust the instruction sequence (and, by extension, things on the execution stack).

#### Branching

For the purposes of limiting the exponential path explosion when a loop node needs to be processed, an upper bound is set for the number of iterations (see `loop_max_iter_count`) with exponential reduction (see `loop_reduction_factor`) based on current total loop nesting depth (i.e. across function/method calls).

Additionally, in order to handle similar issue with excessive use of conditional branching in general a similar strategy was used - "branching budget".
This parameter (see `branching_budget` for `PathEnumerator.explore`) sets an upper bound on the exploration depth, decrementing by 1 at every splitting point in the control flow graph (this includes loops, conditionals, `throw`s; but not with virtual calls - see below).

#### Subroutine calls

Each static call node is replaced with a copy of the function's implementation with following nodes attached at its last node.
The name of the function being called is placed on top of path's "call stack".
The size of that "simulated call stack" is controlled by `call_stack_max_depth` exploration config field.
A "failure" path is generated when such limit is exceeded.

In order to handle virtual calls the `TypeHierarchyResolver` class functionality is utilized (see `micro_svm.type_hierarchy`).
This class builds an internal representation of class-hierarchy relationships of structures/classes of a given specification.
This class allows for:

- Resolving a method (given structure and method name) into a collection of function names that are actual implementations with respect to class type hierarchy.
- Retrieving the list of all parents for a structure/class.
- Resolving class field origin (i.e., first class a given field was first declared; there might be issues with field shadowing).
- Retrieving all fields (including inherited ones).
- Retrieving concrete implementations (i.e., static function name) for all methods of a given class (including inherited ones).

Each static candidate call target is being processed as a regular static call with instance reference type check (expecting exact match) added before as a single basic block with a control node (for early stopping when checking path validity).
For example, if classes `Foo` and `Bar` both implement abstract `Object.act` method then during in-place call target resolution step, `Object.act` call would be equivalent to directly calling `Foo.act` and `Bar.act` respectively.
Thus, a single virtual call node is being expanded as a collection of paths with distinct static function calls.
It's important to note that `TypeHierarchyResolver` instance should be properly initialized and have `analyze`-d the user specification **before** starting program path exploration process.
Another important point is that it handles classes with multiple parents the same way Python does (i.e. looks up first implementation in the declaration order specified in the `parents` list, see `StructureTypeInfo` in `micro_svm.types`).

#### Exception management

Upon encountering a `try-block` node, an *exception handler table* object is initialized with the current "stack frame" information (total loop depth/level, call stack size, current total level of `try-block` nesting) and then placed on top of the current path's *exception handling stack*.
Each handler entry in that table is prepared by cloning the isolated handler branch and attaching a "follower" - the `finally` handler and/or the one going exactly after the `try-block`.
It's important to note that a unique *boundary* value is put on top of the execution stack (and removed after "leaving" the `try-block` "body" section) in order to "dynamically" handle the cross-procedural nature of exceptions (i.e. managing values pushed on the stack during subroutine "execution" that are needed to be "cleaned-up/discarded" when an exception is `throw`-n).
Matching *boundary* value is used when exiting from the matching `try-block` (with a special "marker" node that is usually not present in a serialized form).

The `throw` node is where all the exception "handling" magic happens.
First, the current **list** of exception handlers is constructed based on the current path's *exception handling stack* (with the `final`/"wildcard" catch handler last if present).
Then, if the "wildcard" handler is absent, it explores a new "unhandled exception" failing path.
After that, for every exception handler it constructs a new path continuation which starts with a basic block containing the exception type guard expression, then an appropriate amount of stack managing flags and instructions with the appropriate handler's implementation sequence (prepared earlier, see the mechanism of the `try-block` above).

A critical part is that handling of `try-block` and `throw` should be synchronized.
It is also important to note that the overall exception management is expecting the raised exception object to not be `null`, i.e., `0` (similar to how Java does this).
Thus, the program spec is expected to have appropriate handling of such cases when relevant.

### Path 'execution'

Each path through the program that is being analyzed consists of a series of instructions (see `micro_svm.instructions`) as mentioned above.
Such paths are suitable for direct "execution" or "validation".
The `SymbolicStateMachine` class specializes exactly in checking this property (see `micro_svm.execution`).
A path is dispatched for execution by using `execute(Instruction[])`, `play(Instruction[])` or `step(Instruction)` methods.
Each instruction is routed to its handler via `getattr(self, instruction.__class__.__name__, None)` approach
(i.e., `PushPrimitive` instruction would be routed to the `visit_instruction_PushPrimitive(PushPrimitive)` method and so on, see `InstructionResolver` implementation in `micro_svm.instructions`).

The `MachineConfig` object allows for direct control over the underlying process and exposes direct access to fine-grained solver-related optimization parameters.

Important design consideration: the `SymbolicStateMachine` performs operations/instructions with a generic stack of values (absolutely real, non-symbolic plain-old Python `list` instance) in mind.
The whole *instruction set* is centered around that idea (similar to how JVM/.NET IL is designed).
This makes translation of the "program" into Z3 expressions easy.
Thou "exception handling" is a bit messy because of that hybrid semi-symbolic approach.

#### Variable and Argument handling

One of the challenges of working with solvers is the inability to change the value of a variable.
Instead you need to create a new one with the same type and assign a new value to it.
This is what SSA is for; every assignment is done once.
Thus, the `VersionedVariable` (for keeping track of versions of the same variable) and `VariableCache` (for translating a specific version of a variable into a solver-friendly expression) classes were created to handle.
Complete information (name, type that is declared in `micro_svm.types`, tags) about a variable is described via `VariableInfo` class (see `micro_svm.descriptors`) and is a part of `GlobalContext` (collection of global variables, see `micro_svm.global_context`).

An example of *updating* the current value of a (**global** in this case) variable as a "raw" Z3 expression (the expression that will be sent to the solver) would look like this:

```text
variable:1 == variable:0 + 5
```

Here we are using *previous* version of the variable, `variable:0`, and saying that the *latest* version of the variable, `variable:1`, should have *that* value ("old + 5" in this case).
References to these "versions" are stored in `VariableCache` instance.

Function **parameters** and **local** variables are declared as global (registered) *symbols* and are resolved dynamically based on the current stack frame number:

```text
value == (#frame)function#~local1:0
```

There are special *marker* instructions `SubroutineEnter` and `SubroutineExit` that are used to manage stack frame information correctly.

In order to slightly improve performance in cases of heavy parameters, local and global variable use a simple *"last assigned literal"* substitution is applied when a *read* operation is performed.

#### Types

There is a limited set of primitive types supported by the machine:

- `boolean`,
- `integer` and `int8/16/32/64` (although bit-specific operations were not tested),
- `real`,
- `string` and `char`,
- `ref<T>` (typed) and `reference` (opaque, serialized as just `ref`, internally the same as `integer`).

Other than primitives there are also *containers* and *structures* (can be considered *classes* in some use cases as functions can be *bound* to structures becoming *methods*).

#### Object instances

The symbolic state machine creates a unique reference/pointer (of just an `integer` type) when handling `NewInstance` by incrementing internal counter.
After that, it asserts the type information (`@object-types` array) associated with that new reference and container size (`@collection-sizes` array) if applicable (for objects/structures it's just `-1`) without making updates to both.
This would look like the following (note that `NULL`/`0` has a unique type ID of `Unit(0)`, the same ID is assigned when handling of `FreeInstance` instruction):

```text
@object-types:0[ptr] == Concat(Unit(UID_1), Unit(UID_2), ..., Unit(UID_n))
@collection-sizes:0[ptr] == -1
```

Then for every field the object/class/structure has, it asserts its default value depending on the field type (the same `@fields$<struct>.<field>` array family is used for accessing field values when handling `FieldRead` and `FieldWrite`), again avoiding explicit updates to the underlying array:

```text
@fields$std.String.value:0[ptr] == ""
```

Checking `InstanceOf` of an object is pretty straightforward:
each type identifier is an Z3 sequence of unique integer identifiers that is a complete list of *every* class/structure that object instance inherits (including itself).
Each sequence is ordered for making exact matches easier.
The expression for solver may look like this (`12345` is a UID that is associated with the requested structure type):

```text
Contains(@object-types:0[ptr], Unit(12345))
```

The machine stores mappings in **both** directions between UID and *type-ID names*, eg., `<type-id>my.Foo</type-id> <=> 12345`.
This information is useful when doing full model decoding for converting internal solver (concrete) symbolic model into actionable Python objects (see `micro_svm.decoding`).

Additionally, it is sometimes useful to know what types of objects and containers were instantiated during a particular path.
For this purpose the state machine also collects `SymbolicStateMachineStatistics`.

#### Container modelling

There are 4 built-in container types supported by the symbolic state machine: arrays, sets, maps and transforms (a special variant of map that has no size and behaves like a symbolic "function" with a single argument).
Instance initialization for them is very similar to a normal object init procedure with a safeguard added when applicable (arrays).

```text
size >= 0
@object-types:0[ptr] == "<type-id>array<integer></type-id>"
@collection-sizes:0[ptr] == size
```

For each container kind there is a family of array-type variables used internally by the machine:

- `@arrays$<item-type>` for arrays.
- `@sets$<item-type>` for sets.
- `@maps$<key>+<value>` for maps.
- `@transforms$<key>+<value>` for transforms.

When retrieving elements of a specific container instance, one of the following expressions would be used internally (note that for `map` type the `key` and `ptr` arguments are expected (but not required) to be non-symbolic and `value` is a temporary uninitialized symbolic variable for holding/receiving the result, i.e., we are asserting that `key`-`value` pair exists for the `ptr` instance):

```text
value == @arrays$integer:0[ptr][index]
@sets$integer:0[ptr][item] == True
@maps$integer+integer:0[ptr][key, value] == True
value == @transforms$integer+integer:0[ptr][key]
```

Symbolic state machine also supports performing updates for all of the above container types.
For example, when doing element update on an array, the following expressions would be used (simplified):

```text
ForAll([p], (p != dst)   => (@arrays$integer:1[p]      == @arrays$integer:0[p]))
ForAll([i], (i != index) => (@arrays$integer:1[dst][i] == @arrays$integer:0[dst][i]))
@arrays$integer:1[dst][index] == value
```

Some of the operations are more complex than others (eg., both `set<T>` and `map<K,V>` also update their container sizes in a single instruction).

#### Faults and Exceptions

There is always a possibility that a *fault*, a form of an unintended and (sometimes) undesired outcome, would be present in a specification.
For managing this, a global flag variable `@fault-flag` was introduced with a couple of *safeguard* expressions added in operations widely known to be sources of erroneous behavior (field access, operations on collections, type mismatches, etc.).
It is handled with `FaultStatusRead` and `FaultStatusClear` instructions.
For configuring the handling of faults see `FaultMode` enum.

Since exception handling was made into the design of the project, a global variable `@last-exception` of type `ref` was introduced for storing thrown exception objects *temporarily*.
For accessing it, two special instructions were introduced: `ExceptionRead` and `ExceptionWrite`.

## Defect detection

> [DISCLAIMER]
>
> This is not a production-ready solution but more of a "proof-of-concept" and thus was implemented as simple as possible
> (thou the whole project is a "PoC").

This one was a nice "bonus-feature" that allowed the demonstration of a somewhat "closed-loop ecosystem" of a pair/system of tools, one of which finds a problem while providing the inputs that caused it, and another one checks if this problematic state is possible to achieve and how to do it.

There is a `DefectAnalyzer` class (see `micro_svm.defect_detection`) that essentially relies on the `PathEnumerator` to produce paths that lead to an error - an exception being not caught correctly, a potential infinite recursion being present (to a degree), etc.

This class utilizes two tactics for reducing the overall state that is producing a failure:

- Reducing the number of *unique instances* of objects.
- Reducing the *maximum size* allowed for any container to have.

While using any of these tactics, the maximum size of containers is kept so it always discourages container growth.

An example of a program's state that leads to an error in `std.List.equals` method specification would look like this:

```json
{
    "global-variables": {},
    "expected-objects": [
        "#000"
    ],
    "allow-object-reuse": true,
    "all-objects": {
        "#000": {
            "type": {
                "_": "structure",
                "name": "std.List"
            },
            "state": {
                "items": "#001"
            }
        },
        "#001": {
            "type": {
                "_": "array",
                "item": {
                    "_": "ref"
                }
            },
            "state": [
                "#000"
            ]
        }
    }
}
```

This auto-generated sample shows an object (a structure) "#000" of type `std.List`.
The field `items` of object "#000" refers to an instance of an array of references "#001".
This array also refers back to the object "#000".
This sample was produced by the "defect detection" functionality for the function/method `std.List.equals` demonstrating an (intentional) issue in the implementation that leads to a "stack overflow" error due to a call to `std.Object.equals` method on elements of the array.

In addition to that, the `DefectAnalyzer` class also prints out some information about the objects that it has managed to decode (see `/examples/defect_detection/classes/list.output-sample.log` for the full output):

```text
[i] Exploring.
[i] Found: 1 potential failing path(s).
[!] Failure found: #stack-overflow
[i] Optimizing...
[i] Decoding state...
[~] Structures: 12
[~] Collections: 10 (max size = 49)
[i] Applying reduction tactic #1...
...
[i] Refining...
#000 : struct='std.List' = {'items': '#001'}
#001 : array<ref> = (1) ['#000']
[i] Example: #000.equals(#000)
```

## Known limitations

- **Limited functionality.**
    This project does not model an existing language but rather utilizes some well-established features and concepts present in some production-grade languages.
    Each user-generated specification is required to include and model the desired language-specific aspects accordingly with respect to existing SVM's supported features.

- **Lack of information-flow tracking.**
    The current implementation focuses on path feasibility rather than information flow (i.e., *"Where did this specific value originate?"*).
    Thus, it may not be well suited for tasks like taint analysis or data-dependency modeling.

- **Type system simplification.**
    The symbolic VM delegates type-checking and coercion to the SMT solver rather than implementing a formal type-checker.
    This simplifies things quite a bit but requires the end-user to provide "well-formed" specifications.
