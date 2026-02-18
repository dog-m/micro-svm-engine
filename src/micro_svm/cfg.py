from abc import ABC, abstractmethod
from typing import Callable, final

from .instructions import Instruction

EXCEPTION_MATCHER_ALL = '*'


class Node(ABC):
    """
    A common dummy node for building control-flow graph.
    """
    __slots__ = ('next',)

    def __init__(self) -> None:
        self.next: Node | None = None

    def has_next(self) -> bool:
        return self.next is not None

    def get_last(self) -> 'Node':
        node = self
        while True:
            if not node.next:
                return node
            node = node.next

    @abstractmethod
    def clone_self(self, dup_instructions: bool = False) -> 'Node': ...

    def clone(self, dup_instructions: bool = False) -> 'Node':
        s_clone = self.clone_self(dup_instructions)
        s_clone.next = None if self.next is None else self.next.clone(dup_instructions)
        return s_clone


class MarkerNode(Node, ABC):
    __slots__ = tuple()


@final
class BasicBlock(Node):
    """
    A simple sequence of instructions.
    """
    __slots__ = ('instructions',)

    def __init__(self) -> None:
        super().__init__()
        self.instructions: list[Instruction] = []

    def clone_self(self, dup_instructions: bool = False):
        bb = BasicBlock()
        bb.instructions.extend(
            self.instructions.copy() if dup_instructions else self.instructions
        )
        return bb


@final
class FailurePath(MarkerNode):
    """
    A marker node that forces the path traversal to finish this path, treating it as a ***failing*** candidate.
    """
    __slots__ = ('metadata',)

    def __init__(self, metadata: str | None) -> None:
        super().__init__()
        self.metadata = metadata

    def __str__(self) -> str:
        return f"<marker: failure [metadata: {repr(self.metadata)}]>"

    def clone_self(self, dup_instructions: bool = False):
        return FailurePath(self.metadata)


@final
class EndOfProgram(MarkerNode):
    """
    A marker node that forces the path traversal to finish this path, treating it as a ***normal*** candidate.
    """
    __slots__ = tuple()

    def __init__(self) -> None:
        super().__init__()

    def __str__(self) -> str:
        return '<marker: end-of-program>'

    def clone_self(self, dup_instructions: bool = False):
        return EndOfProgram()


@final
class CallStatic(Node):
    """
    A call to a static function. Arguments will be pulled from the top of the stack automatically.
    """
    __slots__ = ('function_name', 'argument_count')

    def __init__(self, signature: str, argc: int) -> None:
        super().__init__()
        self.function_name = signature
        self.argument_count = argc

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [func={self.function_name}, argc={self.argument_count}]"

    def clone_self(self, dup_instructions: bool = False):
        return CallStatic(self.function_name, self.argument_count)


@final
class CallVirtual(Node):
    """
    A call to an instance method. Arguments will be pulled from the top of the stack automatically.
    """
    __slots__ = ('structure_name', 'method_name', 'argument_count')

    def __init__(self, structure: str, method: str, argc: int) -> None:
        super().__init__()
        self.structure_name = structure
        self.method_name = method
        self.argument_count = argc

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [func={self.structure_name}.{self.method_name}, argc={self.argument_count}]"

    def clone_self(self, dup_instructions: bool = False):
        return CallVirtual(self.structure_name, self.method_name, self.argument_count)


@final
class MarkerFunctionExit(MarkerNode):
    """
    A marker node that signals about reaching the end of a subroutine call.
    """
    __slots__ = tuple()

    def __init__(self) -> None:
        super().__init__()

    def __str__(self) -> str:
        return '<marker: function-exit>'

    def clone_self(self, dup_instructions: bool = False):
        return MarkerFunctionExit()


@final
class If(Node):
    """
    A simple branching node.
    """
    __slots__ = ('condition', 'branch_true', 'branch_false')

    def __init__(self, cond: Node, b_true: Node, b_false: Node | None) -> None:
        super().__init__()
        assert cond and b_true
        self.condition = cond
        self.branch_true = b_true
        self.branch_false = b_false

    def clone_self(self, dup_instructions: bool = False):
        return If(
            self.condition.clone(dup_instructions),
            self.branch_true.clone(dup_instructions),
            self.branch_false.clone(dup_instructions) if self.branch_false is not None else None
        )


@final
class While(Node):
    """
    A branching node for making 'while'-style loops.
    """
    __slots__ = ('loop_id', 'condition', 'body')

    def __init__(self, loop_id: int | str, cond: Node, body: Node) -> None:
        super().__init__()
        assert cond is not None
        assert body is not None
        self.loop_id = loop_id
        self.condition = cond
        self.body = body

    def clone_self(self, dup_instructions: bool = False):
        return While(
            self.loop_id,
            self.condition.clone(dup_instructions),
            self.body.clone(dup_instructions)
        )


@final
class MarkerLoopEnd(MarkerNode):
    """
    A marker node that signals about reaching the end of a single iteration in a loop.
    """
    __slots__ = ('loop_id',)

    def __init__(self, loop_id: int | str):
        super().__init__()
        self.loop_id = loop_id

    def __str__(self) -> str:
        return f"<marker: loop-end [loop=#{self.loop_id}]>"

    def clone_self(self, dup_instructions: bool = False):
        return MarkerLoopEnd(self.loop_id)


@final
class MarkerLoopIterationEnd(MarkerNode):
    """
    A marker node that signals about reaching the end of a single iteration in a loop.
    """
    __slots__ = ('loop_id',)

    def __init__(self, loop_id: int | str):
        super().__init__()
        self.loop_id = loop_id

    def __str__(self) -> str:
        return f"<marker: loop-iter-end [loop=#{self.loop_id}]>"

    def clone_self(self, dup_instructions: bool = False):
        return MarkerLoopIterationEnd(self.loop_id)


@final
class Break(Node):
    """
    A regular 'break' instruction but for path generation/exploration.
    """
    __slots__ = ('loop_id',)

    def __init__(self, loop_id: int | str):
        super().__init__()
        self.loop_id = loop_id

    def __str__(self) -> str:
        return f"<break> [loop=#{self.loop_id}]"

    def clone_self(self, dup_instructions: bool = False):
        return Break(self.loop_id)


@final
class Continue(Node):
    """
    A regular 'continue' instruction but for path generation/exploration.
    """
    __slots__ = ('loop_id',)

    def __init__(self, loop_id: int | str):
        super().__init__()
        self.loop_id = loop_id

    def __str__(self) -> str:
        return f"<continue> [loop=#{self.loop_id}]"

    def clone_self(self, dup_instructions: bool = False):
        return Continue(self.loop_id)


@final
class TryBlock(Node):
    """
    A regular "try-catch-finally" block.
    The "execution" of nodes inside of the "body" node is guarded by the set of "catch-handlers" and/or "finishing section".
    """
    __slots__ = ('body', 'catch_handlers', 'finishing_section')

    def __init__(self, body: Node) -> None:
        super().__init__()
        assert body is not None
        self.body = body
        self.catch_handlers: dict[str, Node] = {}
        self.finishing_section: Node | None = None

    def clone_self(self, dup_instructions: bool = False):
        node = TryBlock(self.body.clone(dup_instructions))
        node.finishing_section = None if self.finishing_section is None else self.finishing_section.clone(dup_instructions)
        for struct_name, handler in self.catch_handlers.items():
            node.catch_handlers[struct_name] = handler.clone(dup_instructions)
        return node


@final
class MarkerTryBlockEnd(MarkerNode):
    """
    A marker node that signals about reaching the end of a guarded body in a try-block.
    """
    __slots__ = tuple()

    def __init__(self):
        super().__init__()

    def __str__(self) -> str:
        return '<marker: try-end>'

    def clone_self(self, dup_instructions: bool = False):
        return MarkerTryBlockEnd()


@final
class Throw(Node):
    """
    A node that explores exception propagation in the context of error handlers set up by the "try-block" node.
    """
    __slots__ = tuple()

    def __init__(self) -> None:
        super().__init__()

    def __str__(self) -> str:
        return '<throw-exception>'

    def clone_self(self, dup_instructions: bool = False):
        return Throw()



@final
class CFGNodeResolver:
    def __init__(self, visitor: object, *, default_handler: Callable[[Node], object | None] | None = None) -> None:
        assert visitor is not None
        self.visitor = visitor
        self.default_handler = default_handler

    def visit(self, node: Node) -> object | None:
        name = f"visit_CFG_{node.__class__.__name__}"
        if (method := getattr(self.visitor, name, None)) is not None:
            return method(node)
        elif self.default_handler is not None:
            return self.default_handler(node)
        else:
            raise AssertionError(f"Unable to find method '{name}' in visitor")

    def visit_chain(self, starting_node: Node | None) -> object | None:
        res = None
        while starting_node is not None:
            res = self.visit(starting_node)
            starting_node = starting_node.next
        return res



class ProgramVisualiser:
    TAB = ' ' * 4

    def __init__(self, printer: Callable[[str], None] = print):
        self.indent = 0
        self.indent_str: str = ''
        self.resolver = CFGNodeResolver(self, default_handler=self.simple)
        self.printer = printer

    def simple(self, value: object) -> None:
        self.printer(f"{self.indent_str}{value}")

    def update_indentation(self, delta: int) -> None:
        self.indent += delta
        assert self.indent >= 0
        self.indent_str = self.TAB * self.indent

    def show(self, title: str, branch: Node | None) -> None:
        self.simple(f"{title}:")
        self.update_indentation(+1)
        if branch is None:
            self.simple('<abstract>')
        else:
            self.resolver.visit_chain(branch)
        self.update_indentation(-1)

    def visit_CFG_BasicBlock(self, node: BasicBlock) -> None:
        for inst in node.instructions:
            self.simple(inst)

    def visit_CFG_If(self, node: If) -> None:
        self.show('if', node.condition)
        self.show('then', node.branch_true)
        if node.branch_false is not None:
            self.show('else', node.branch_false)

    def visit_CFG_While(self, node: While) -> None:
        self.show(f"while [#{node.loop_id}]", node.condition)
        self.show('body', node.body)

    def visit_CFG_TryBlock(self, node: TryBlock) -> None:
        self.show("try", node.body)
        for struct_name, handler in node.catch_handlers.items():
            self.show(f"catch [struct={repr(struct_name)}]", handler)
        if node.finishing_section is not None:
            self.show('finally', node.finishing_section)

