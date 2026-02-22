from typing import Iterable, cast, final

from .cfg import *  # noqa: F403
from .descriptors import CompiledSubroutine
from .global_context import GlobalContext
from .instructions import (
    Assume,
    ClearStackToBoundary,
    ControlPoint,
    Copy,
    ExceptionRead,
    InstanceOf,
    Pop,
    PrimitiveOp,
    PrimitiveOps,
    PushPrimitive,
    PushStackBoundary,
    StackBoundary,
    SubroutineExit,
)
from .type_hierarchy import TypeHierarchyResolver
from .types import reference


@final
class Program:
    def __init__(self, ctx: GlobalContext, main: CompiledSubroutine) -> None:
        self.context = ctx
        self.main_subroutine = main



@final
class ProgramPath:
    def __init__(self, steps: list[BasicBlock]) -> None:
        self.steps = steps
        self.end_is_reached: bool = False

    def instructions(self) -> Iterable[Instruction]:
        self.end_is_reached = False
        for block in self.steps:
            for inst in block.instructions:
                yield inst
        self.end_is_reached = True

    def get_trace(self, *, prefix = '', suffix = '') -> str:
        lines = [
            str(inst)
            for inst in self.instructions()
        ]
        return f"{prefix}{'\n'.join(lines)}{suffix}"



@final
class EnumeratorFailureMetadataTags:
    def __init__(self):
        self.unhandled_exception: str = '#unhandled-exception'
        self.stack_overflow: str      = '#stack-overflow'



@final
class EnumeratorConfig:
    def __init__(self):
        self.loop_max_iter_count: int     = 17
        self.loop_reduction_factor: float = 10.0
        self.path_max_count: int          = 2 ** 10
        self.call_stack_max_depth: int    = 5  # third of loops
        self.failure_tags = EnumeratorFailureMetadataTags()

    def get_loop_iterations_limit(self, level: int) -> int:
        res = self.loop_max_iter_count / self.loop_reduction_factor ** level
        return int(res)



@final
class ExceptionHandlingTable:
    def __init__(self):
        self.handlers: dict[str, Node]  = {}
        self.handler_stack_frame_number = 0
        self.handler_try_block_number   = 0
        self.loop_level                 = 0
        self.boundary                   = StackBoundary()



@final
class PathEnumerator:
    """
    Stack-based DFS path enumeration utility.
    """

    class Path:
        def __init__(self, node: Node, budget: int = 0):
            self.next_node = node
            self.budget = budget
            self.steps: list[BasicBlock] = []
            self.branch_id_stack: list[str] = []
            self.loop_level: int = 0
            self.call_stack: list[str] = []
            self.exception_handler_stack: list[ExceptionHandlingTable] = []

        def clone(self) -> 'PathEnumerator.Path':
            p = PathEnumerator.Path(self.next_node, self.budget)
            p.steps                   = self.steps.copy()
            p.branch_id_stack         = self.branch_id_stack.copy()
            p.loop_level              = self.loop_level
            p.call_stack              = self.call_stack.copy()
            p.exception_handler_stack = self.exception_handler_stack.copy()
            return p

        def update_loop_level(self, delta: int) -> None:
            self.loop_level += delta

        def backup_branch_markers(self) -> list[str]:
            return self.branch_id_stack.copy()

        def restore_branch_markers(self, id_stack: list[str]) -> None:
            self.branch_id_stack.clear()
            self.branch_id_stack.extend(id_stack)


    def __init__(self, program: Program, resolver: TypeHierarchyResolver) -> None:
        self.program = program
        self.config = EnumeratorConfig()
        self.session_prefix: str = ''
        self.on_complete_path: Callable[[ProgramPath, 'PathEnumerator'], None] | None = None
        self.on_failing_path: Callable[[ProgramPath, 'PathEnumerator', str | None, list[str]], None] | None = None
        self.on_extinguished_path: Callable[['PathEnumerator'], None] | None = None
        #
        self._node_resolver = CFGNodeResolver(self)
        self._th_resolver = resolver
        self._paths_to_explore: list[PathEnumerator.Path] = []
        self._current_path: PathEnumerator.Path = None
        self._is_exploring: bool = False
        self._paths_produced = 0


    def stop_exploration(self) -> None:
        self._is_exploring = False


    def explore(self, branching_budget: int = 10) -> None:
        self._is_exploring = True
        self._paths_produced = 0

        self._paths_to_explore.append(PathEnumerator.Path(self.program.main_subroutine.entry_node, branching_budget))
        while self._is_exploring and self._paths_to_explore:
            self._current_path = self._paths_to_explore.pop()
            self._node_resolver.visit(self._current_path.next_node)

        # TODO: should there "on_extinguished" callback be triggered here too or not?
        self._paths_to_explore.clear()


    def _push_control_node_id(self, name: str) -> object:
        stack = self._current_path.branch_id_stack
        if not stack:
            stack.append(self.session_prefix)
        stack.append(name)
        res = ''.join(stack)
        #print('[~]', res, flush=True)
        return res


    def _continue_along(self, next_node: Node | None) -> None:
        if next_node is not None:
            self._current_path.next_node = next_node
            self._paths_to_explore.append(self._current_path)
        # failsafe
        self._current_path = None


    def _branch_along(self, next_node: Node, cost: int = 1) -> None:
        budget = self._current_path.budget - cost
        if budget >= 0:
            path = self._current_path.clone()
            path.next_node = next_node
            path.budget = budget
            self._paths_to_explore.append(path)
        else:
            if self.on_extinguished_path is not None:
                self.on_extinguished_path(self)


    def _skip_until(self, start: Node | None, target_condition: Callable[[Node], bool]) -> Node | None:
        while start is not None and not target_condition(start):
            start = start.next
        return start


    # === [node processing] ==========================

    def _can_produce_more_paths(self) -> bool:
        res = self._paths_produced < self.config.path_max_count
        if res:
            self._paths_produced += 1
        else:
            print('[!] Explored too many valid potential paths. Giving up.')
            self.stop_exploration()
        return res


    def visit_CFG_FailurePath(self, node: FailurePath) -> None:
        if self.on_failing_path is not None:
            if self._can_produce_more_paths():
                stack = self._current_path.call_stack
                self.on_failing_path(ProgramPath(self._current_path.steps), self, node.metadata, stack)


    def visit_CFG_EndOfProgram(self, _: EndOfProgram) -> None:
        if self.on_complete_path is not None:
            if self._can_produce_more_paths():
                self.on_complete_path(ProgramPath(self._current_path.steps), self)


    def visit_CFG_BasicBlock(self, node: BasicBlock) -> None:
        self._current_path.steps.append(node)
        self._continue_along(node.next)


    def visit_CFG_If(self, node: If) -> None:
        # assemble and schedule the path along the 'False' branch first
        if node.branch_false is None:
            condition = node.condition.clone()
            control_node = condition.get_last().next = BasicBlock()
            control_node.instructions.extend([
                PrimitiveOp(PrimitiveOps.NOT),
                Assume(),
                ControlPoint(self._push_control_node_id('F')),
            ])
            control_node.next = node.next
            # ===
            self._branch_along(condition)
            self._current_path.branch_id_stack.pop()  # restore for the other branch

        else:
            condition = node.condition.clone()
            branch    = node.branch_false.clone()
            control_node = condition.get_last().next = BasicBlock()
            control_node.instructions.extend([
                PrimitiveOp(PrimitiveOps.NOT),
                Assume(),
                ControlPoint(self._push_control_node_id('F')),
            ])
            control_node.next = branch
            branch.get_last().next = node.next
            # ===
            self._branch_along(condition)
            self._current_path.branch_id_stack.pop()  # restore for the other branch

        # assemble the path along the 'True' branch
        condition = node.condition.clone()
        branch    = node.branch_true.clone()
        control_node = condition.get_last().next = BasicBlock()
        control_node.instructions.extend([
            Assume(),
            ControlPoint(self._push_control_node_id('T')),
        ])
        control_node.next = branch
        branch.get_last().next = node.next
        # ===
        self._branch_along(condition)


    def visit_CFG_MarkerLoopIterationEnd(self, node: MarkerLoopIterationEnd) -> None:
        # just moving forward
        self._continue_along(node.next)


    def visit_CFG_MarkerLoopEnd(self, node: MarkerLoopEnd) -> None:
        self._current_path.update_loop_level(-1)
        self._continue_along(node.next)


    def visit_CFG_While(self, node: While) -> None:
        markers_backup = self._current_path.backup_branch_markers()

        max_iter_count = self.config.get_loop_iterations_limit(self._current_path.loop_level)
        self._current_path.update_loop_level(+1)

        for iter_count in range(max_iter_count, -1, -1):
            # managing markers
            self._current_path.restore_branch_markers(markers_backup)

            # main sequence of un-folded iterations
            subpath_head: Node | None = None
            subpath_tail = subpath_head
            for _ in range(iter_count):
                condition = node.condition.clone()
                body      = node.body.clone()
                # ===
                if subpath_tail is None:
                    subpath_head = condition
                else:
                    subpath_tail.next = condition
                # ===
                control_node = condition.get_last().next = BasicBlock()
                control_node.instructions.extend([
                    Assume(),
                    ControlPoint(self._push_control_node_id('T')),
                ])
                control_node.next = body
                subpath_tail = body.get_last().next = MarkerLoopIterationEnd(node.loop_id)

            # ending break
            condition = node.condition.clone()
            # ===
            if subpath_tail is None:
                subpath_head = condition
            else:
                subpath_tail.next = condition
            # ===
            control_node = condition.get_last().next = BasicBlock()
            control_node.instructions.extend([
                PrimitiveOp(PrimitiveOps.NOT),
                Assume(),
                ControlPoint(self._push_control_node_id('F')),
            ])
            break_marker = control_node.next = MarkerLoopEnd(node.loop_id)
            break_marker.next = node.next
            # ===
            self._branch_along(subpath_head, cost=max(1, iter_count))


    def visit_CFG_Break(self, node: Break) -> None:
        end_marker = self._skip_until(
            node,
            lambda n: isinstance(n, MarkerLoopEnd) and cast(MarkerLoopEnd, n).loop_id == node.loop_id
        )
        self._continue_along(end_marker)  # it is important to pass by the marker


    def visit_CFG_Continue(self, node: Continue) -> None:
        end_marker = self._skip_until(
            node,
            lambda n: isinstance(n, MarkerLoopIterationEnd) and cast(MarkerLoopIterationEnd, n).loop_id == node.loop_id
        )
        self._continue_along(end_marker)  # it is important to pass by the marker


    # TODO: there might be a problem with in what order each argument is being executed
    def visit_CFG_CallStatic(self, node: CallStatic) -> None:
        fname = node.function_name
        stack = self._current_path.call_stack
        c = self.config
        if len(stack) < c.call_stack_max_depth:
            stack.append(fname)
            # ===
            func = self.program.context.functions[fname]
            impl_entry = func.implementation.entry_node.clone()
            impl_exit = impl_entry.get_last().next = MarkerFunctionExit()
            impl_exit.next = node.next
            # ===
            self._continue_along(impl_entry)

        else:
            # path is too long - probably an instance of infinite recursion
            terminator = FailurePath(c.failure_tags.stack_overflow)
            # ===
            self._continue_along(terminator)


    def visit_CFG_CallVirtual(self, node: CallVirtual) -> None:
        stack = self._current_path.call_stack
        c = self.config
        if len(stack) < c.call_stack_max_depth:
            # function name would be added onto the stack later during the static call
            # ===
            candidates = self._th_resolver.get_virtual_call_targets(node.structure_name, node.method_name)

            # branching-off
            markers_backup = self._current_path.backup_branch_markers()
            for i, (type_guard, impl_name) in enumerate(candidates.items()):
                # managing markers
                self._current_path.restore_branch_markers(markers_backup)
                # ===
                check = BasicBlock()
                check.instructions.extend([
                    # WARNING: expecting instance ptr to be the first argument!
                    # (note: last one is currently lays down on top of the stack, i.e., reaching deeper for the first one)
                    Copy(index=node.argument_count - 1),
                    InstanceOf(type_guard, exact=True),
                    Assume(),
                    ControlPoint(self._push_control_node_id(f"|{i}|")),
                ])
                call = check.next = CallStatic(impl_name, node.argument_count)
                call.next = node.next
                # ===
                self._branch_along(check, cost=0)

        else:
            # path is too long - probably an instance of infinite recursion
            terminator = FailurePath(c.failure_tags.stack_overflow)
            # ===
            self._continue_along(terminator)


    def visit_CFG_MarkerFunctionExit(self, node: MarkerFunctionExit) -> None:
        self._current_path.call_stack.pop()
        # ===
        self._continue_along(node.next)


    def visit_CFG_TryBlock(self, node: TryBlock) -> None:
        table = ExceptionHandlingTable()
        table.loop_level                 = self._current_path.loop_level
        table.handler_stack_frame_number = len(self._current_path.call_stack)
        table.handler_try_block_number   = len(self._current_path.exception_handler_stack)
        self._current_path.exception_handler_stack.append(table)

        follower = node.next
        if node.finishing_section is not None:
            follower = node.finishing_section.clone()
            follower.get_last().next = node.next

        for struct_name, handler in node.catch_handlers.items():
            h = table.handlers[struct_name] = handler.clone()
            h.get_last().next = follower

        # NOTE: adding "finally" handler at the end!
        if node.finishing_section is not None:
            table.handlers[EXCEPTION_MATCHER_ALL] = follower

        entry = BasicBlock()
        entry.instructions.append(
            PushStackBoundary(table.boundary)
        )
        body = entry.next = node.body.clone()
        closing_marker = body.get_last().next = MarkerTryBlockEnd()
        closing_marker.next = follower
        # ===
        self._continue_along(entry)


    def visit_CFG_MarkerTryBlockEnd(self, node: MarkerTryBlockEnd) -> None:
        table = self._current_path.exception_handler_stack.pop()
        cleaner = BasicBlock()
        cleaner.instructions.extend([
            ClearStackToBoundary(table.boundary),
            Pop()  # removing the stack boundary
        ])
        cleaner.next = node.next
        # ===
        self._continue_along(cleaner)


    def _throw_init_catch_wildcard(self, catch_instructions: list[Instruction], handler_struct_types: list[str]) -> None:
        catch_instructions.extend([
            ExceptionRead(),
            PushPrimitive(0, reference),
            PrimitiveOp(PrimitiveOps.EQ),
        ])
        for struct_name in handler_struct_types:
            if struct_name != EXCEPTION_MATCHER_ALL:
                catch_instructions.extend([
                    ExceptionRead(),
                    InstanceOf(struct_name),
                    PrimitiveOp(PrimitiveOps.OR),
                ])
        catch_instructions.extend([
            PrimitiveOp(PrimitiveOps.NOT),
            Assume(),
            # i.e. "not (err == NULL | err is EFoo | err is EBar | ...)"
            # i.e. "err != NULL & err is not EFoo & ..."
        ])


    def _throw_init_catch_typed(self, catch_instructions: list[Instruction], exception_type: str, handled_struct_types: list[str]) -> None:
        if len(handled_struct_types) == 0:
            catch_instructions.extend([
                ExceptionRead(),
                InstanceOf(exception_type),
                Assume(),
            ])

        else:
            catch_instructions.extend([
                ExceptionRead(),
                PushPrimitive(0, reference),
                PrimitiveOp(PrimitiveOps.EQ),
            ])
            for etype in handled_struct_types:
                catch_instructions.extend([
                    ExceptionRead(),
                    InstanceOf(etype),
                    PrimitiveOp(PrimitiveOps.OR),
                ])

            catch_instructions.extend([
                PrimitiveOp(PrimitiveOps.NOT),

                ExceptionRead(),
                InstanceOf(exception_type),

                PrimitiveOp(PrimitiveOps.AND),
                Assume(),
                # i.e. "not (err == NULL | err is EBar | err is EBazz | ...) & err is EFoo"
                # i.e. "err != NULL & err is EFoo & err is not EBar & ..."
            ])


    def _throw_get_control_signature(self, struct_name: str, handled_exception_types: list[str]) -> str:
        if len(handled_exception_types) == 0 or struct_name == EXCEPTION_MATCHER_ALL:
            return f"<e:{struct_name}>"
        else:
            handled = ' | '.join(handled_exception_types)
            return f"<e:{struct_name} & !({handled})>"


    def _throw_append_markers(self, node: Node, marker: type[MarkerNode], count: int) -> Node:
        for _ in range(count):
            node.next = marker()
            node = node.next
        return node


    def visit_CFG_Throw(self, _: Throw) -> None:
        exception_handlers_ordered: dict[str, tuple[ExceptionHandlingTable, Node]] = {}
        has_wildcard_matcher = False
        for table in reversed(self._current_path.exception_handler_stack):
            for struct_name, handler in table.handlers.items():
                if struct_name not in exception_handlers_ordered:
                    exception_handlers_ordered[struct_name] = (table, handler)

                    if (has_wildcard_matcher := (struct_name == EXCEPTION_MATCHER_ALL)):
                        break
            if has_wildcard_matcher:
                break
        # NOTE: it is generally not possible to know the exact type of exception that is being thrown

        # special case - unhandled exception
        if not has_wildcard_matcher:
            ue_block = BasicBlock()
            self._throw_init_catch_wildcard(ue_block.instructions, exception_handlers_ordered.keys())
            ue_block.next = FailurePath(self.config.failure_tags.unhandled_exception)
            # ===
            self._branch_along(ue_block)

        # regular case - normal catch blocks and top-most "final" block if present
        handled_exception_types: list[str] = []
        markers_backup = self._current_path.backup_branch_markers()
        for struct_name, (table, handler) in exception_handlers_ordered.items():
            # managing markers
            self._current_path.restore_branch_markers(markers_backup)
            # ===
            catch_block = BasicBlock()
            if struct_name == EXCEPTION_MATCHER_ALL:
                self._throw_init_catch_wildcard(catch_block.instructions, exception_handlers_ordered.keys())
            else:
                self._throw_init_catch_typed(catch_block.instructions, struct_name, handled_exception_types)
            # ===
            control_sig = self._throw_get_control_signature(struct_name, handled_exception_types)
            catch_block.instructions.append(
                ControlPoint(self._push_control_node_id(control_sig))
            )
            # ===
            handled_exception_types.append(struct_name)
            # ===
            self._current_path.loop_level = table.loop_level
            delta_call_stack = len(self._current_path.call_stack)              - table.handler_stack_frame_number
            delta_try_block  = len(self._current_path.exception_handler_stack) - table.handler_try_block_number
            for _ in range(delta_call_stack):
                catch_block.instructions.append(
                    SubroutineExit()
                )
            node = catch_block
            node = self._throw_append_markers(node, MarkerFunctionExit, delta_call_stack)
            node = self._throw_append_markers(node, MarkerTryBlockEnd,  delta_try_block)
            node.get_last().next = handler  # the handler should already have an appropriate continuation
            # ===
            self._branch_along(catch_block)


    def visit_CFG_Switch(self, node: Switch) -> None:
        markers_backup = self._current_path.backup_branch_markers()
        processed_conditions: list[Node] = []
        for i, (condition, handler) in enumerate(node.cases):
            # managing markers
            self._current_path.restore_branch_markers(markers_backup)
            # ===
            entry = cond_last = None
            if node.value_source is None:
                entry = cond_last = condition.clone()
            else:
                entry = node.value_source.clone()
                cond_last = entry.get_last().next = condition.clone()
            cond_last = cond_last.get_last()
            # ===
            if node.cumulative:
                # using one-by-one split instead of a single huge expression
                for cond in processed_conditions:
                    cond = cond_last.next = cond.clone()
                    cond_last = cond.get_last()
                    discard = cond_last.next = BasicBlock()
                    discard.instructions.extend([
                        PrimitiveOp(PrimitiveOps.NOT),
                        Assume(),
                    ])
                processed_conditions.append(condition)
            # ===
            control = cond_last.next = BasicBlock()
            control.instructions.extend([
                Assume(),
                ControlPoint(self._push_control_node_id(f"|?{i}|")),
            ])
            control.next = handler
            handler.get_last().next = node.next
            # ===
            self._branch_along(entry)

