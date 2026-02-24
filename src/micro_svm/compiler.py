from typing import final

from .cfg import *  # noqa: F403
from .descriptors import CompiledSubroutine, FunctionInfo, VariableInfo, structure_member_to_signature
from .instructions import *  # noqa: F403
from .types import ValueType, integer, reference


@final
class Readable:
    def __init__(self, *inst: Instruction) -> None:
        assert isinstance(inst, tuple)
        self.instructions = inst

    def __add__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.ADD))

    def __sub__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.SUB))

    def __mul__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.MUL))

    def __div__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.DIV))

    def __truediv__(self, other: 'Readable') -> 'Readable':
        return self.__div__(other)

    def __mod__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.MOD))

    def __and__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.AND))

    def __or__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.OR))

    def __xor__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.XOR))

    def __rshift__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.SHR))

    def __lshift__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.SHL))

    def __eq__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.EQ))

    def __ne__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.NEQ))

    def __lt__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.LESS))

    def __le__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.LEQ))

    def __gt__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.GREATER))

    def __ge__(self, other: 'Readable') -> 'Readable':
        return Readable(*self.instructions, *other.instructions, PrimitiveOp(PrimitiveOps.GEQ))

    def __pos__(self) -> 'Readable':
        return self

    def __neg__(self) -> 'Readable':
        return Readable(*self.instructions, PrimitiveOp(PrimitiveOps.NEGATE))

    def __invert__(self) -> 'Readable':
        return Readable(*self.instructions, PrimitiveOp(PrimitiveOps.NOT))



type PType = PrimitiveTypeInfo
type BranchCallback           = Callable[[], None]
type BranchCallbackWithResult = Callable[[], Readable]

class VariableHandle:
    def __init__(self,
                 name: str, type: PType | None,
                 *,
                 is_local: bool = False) -> None:
        self.name = name
        self.type = type
        self.is_local = is_local



@final
class JoinedHandle:
    def __init__(self, read_handle: Readable, write_handle: VariableHandle):
        self.r = read_handle
        self.w = write_handle


class GraphJunctionBuilder:
    def warn_incomplete(self) -> None: ...



class CompilerContext:
    def __init__(self, func: FunctionInfo | None = None) -> None:
        self.current_function = func
        self.null_ref = self.const(0, reference)
        #
        self._current_block = BasicBlock()
        self._starting_block = self._current_block
        self._ignore_followup_instructions = False
        self._local_variables: list[VariableInfo] = []
        self._loop_uid = 0
        self._loop_id_stack: list[object] = []
        self._incomplete_builders: list[GraphJunctionBuilder] = []


    def build(self) -> CompiledSubroutine:
        if self.current_function is not None:
            init_block = BasicBlock()
            init_block.instructions.append(
                SubroutineEnter()
            )

            # prepare the arguments
            keys = [*self.current_function.parameters.keys()]
            keys.reverse()
            for name in keys:
                param_name = self.current_function.get_full_parameter_name(name)
                init_block.instructions.append(VariableWrite(param_name, True))
            init_block.next = self._starting_block
            self._starting_block = init_block

            # prepare the return value
            if self.current_function.result_type is not None:
                res = self.get_function_result()
                self._add_instructions(
                    *res.r.instructions,
                )

            self._add_instructions(
                SubroutineExit(),
            )

        return CompiledSubroutine(
            self._starting_block,
            self._local_variables.copy()
        )


    def _add_instructions(self, *inst: Instruction) -> None:
        if not self._ignore_followup_instructions:
            #if not isinstance(inst, (tuple, list, set)):
            #    inst = (inst,)
            assert isinstance(self._current_block, BasicBlock)
            self._current_block.instructions.extend(inst)


    def _next_loop_id(self) -> object:
        self._loop_uid += 1
        return self._loop_uid


    def error(self, metadata: str | None = None) -> None:
        if not self._ignore_followup_instructions:
            node = self._current_block.next = FailurePath(metadata)
            self._current_block = node
            self._ignore_followup_instructions = True


    def make_local_variable(self, type: PType, tags: set[str] | None = None) -> JoinedHandle:
        context = '<main>' if self.current_function is None else self.current_function.full_name
        name = f"{context}#~local{len(self._local_variables)}"

        vi = VariableInfo(name, type, None, tags)
        self._local_variables.append(vi)

        vh = VariableHandle(name, type, is_local=True)
        return JoinedHandle(self._read(vh), vh)


    def get_global_variable(self, name: str) -> JoinedHandle:
        assert name and len(name) > 0
        type = None  # TODO: ???
        vh = VariableHandle(name, type)
        return JoinedHandle(self._read(vh), vh)


    def get_parameter(self, name: str) -> JoinedHandle:
        assert name and len(name) > 0
        type = self.current_function.parameters[name]
        name = self.current_function.get_full_parameter_name(name)
        vh = VariableHandle(name, type, is_local=True)
        return JoinedHandle(self._read(vh), vh)


    def get_function_result(self) -> JoinedHandle:
        name = self.current_function.get_full_parameter_name(FunctionInfo.RESULT_NAME)
        type = self.current_function.result_type
        vh = VariableHandle(name, type, is_local=True)
        return JoinedHandle(self._read(vh), vh)


    def const(self, value: object, type: PType = integer) -> Readable:
        return Readable(
            PushPrimitive(value, type),
        )


    def noop(self, comment: str | None = None) -> None:
        self._add_instructions(
            Noop(comment),
        )


    def symbolic(self, type: PType) -> Readable:
        return Readable(
            PushSymbolic(type),
        )


    def _read(self, var: VariableHandle) -> Readable:
        return Readable(
            VariableRead(var.name, var.is_local),
        )


    def write(self, var: VariableHandle, value: Readable) -> None:
        self._add_instructions(
            *value.instructions,
            VariableWrite(var.name, var.is_local),
        )


    def assume(self, expression: Readable) -> None:
        self._add_instructions(
            *expression.instructions,
            Assume(),
        )


    def container_size(self, container_ref: Readable) -> Readable:
        return Readable(
            *container_ref.instructions,
            ContainerGetSize(),
        )


    def array_new(self, item_type: PType, size: Readable) -> Readable:
        return Readable(
            *size.instructions,
            ArrayOperation(ArrayOps.NEW, item_type),
        )


    def array_set_size(self, item_type: PType, array_ref: Readable, size: Readable) -> None:
        self._add_instructions(
            *array_ref.instructions,
            *size.instructions,
            ArrayOperation(ArrayOps.SET_SIZE, item_type),
        )


    def array_get(self, item_type: PType, array_ref: Readable, index: Readable) -> Readable:
        return Readable(
            *array_ref.instructions,
            *index.instructions,
            ArrayOperation(ArrayOps.GET, item_type),
        )


    def array_set(self, item_type: PType, array_ref: Readable, index: Readable, value: Readable) -> None:
        self._add_instructions(
            *array_ref.instructions,
            *index.instructions,
            *value.instructions,
            ArrayOperation(ArrayOps.SET, item_type),
        )


    def array_copy(
            self,
            item_type: PType | None,
            src: Readable, src_index: Readable,
            dst: Readable, dst_index: Readable,
            count: Readable,
            ) -> None:
        self._add_instructions(
            *src.instructions,
            *src_index.instructions,
            *dst.instructions,
            *dst_index.instructions,
            *count.instructions,
            ArrayOperation(ArrayOps.COPY, item_type),
        )


    def array_equals_range(
            self,
            item_type: PType,
            a: Readable, a_index: Readable,
            b: Readable, b_index: Readable,
            count: Readable,
            ) -> Readable:
        return Readable(
            *a.instructions,
            *a_index.instructions,
            *b.instructions,
            *b_index.instructions,
            *count.instructions,
            ArrayOperation(ArrayOps.EQUALS_RANGE, item_type),
        )


    def set_new(self, item_type: PType) -> Readable:
        return Readable(
            SetOperation(SetOps.NEW, item_type),
        )


    def set_contains(self, item_type: PType, set_ref: Readable, item: Readable) -> Readable:
        return Readable(
            *set_ref.instructions,
            *item.instructions,
            SetOperation(SetOps.CONTAINS, item_type),
        )


    def set_add(self, item_type: PType, set_ref: Readable, item: Readable) -> None:
        self._add_instructions(
            *set_ref.instructions,
            *item.instructions,
            SetOperation(SetOps.ADD, item_type),
        )


    def set_get_any(self, item_type: PType, set_ref: Readable) -> None:
        return Readable(
            *set_ref.instructions,
            SetOperation(SetOps.ANY_ITEM, item_type),
        )


    def set_remove(self, item_type: PType, set_ref: Readable, item: Readable) -> None:
        self._add_instructions(
            *set_ref.instructions,
            *item.instructions,
            SetOperation(SetOps.REMOVE, item_type),
        )


    def set_union(self, item_type: PType, in_a: Readable, in_b: Readable, out: Readable) -> None:
        self._add_instructions(
            *in_a.instructions,
            *in_b.instructions,
            *out.instructions,
            SetOperation(SetOps.UNION, item_type),
        )


    def set_intersection(self, item_type: PType, in_a: Readable, in_b: Readable, out: Readable) -> None:
        self._add_instructions(
            *in_a.instructions,
            *in_b.instructions,
            *out.instructions,
            SetOperation(SetOps.INTERSECTION, item_type),
        )


    def set_equals(self, item_type: PType, a: Readable, b: Readable) -> Readable:
        return Readable(
            *a.instructions,
            *b.instructions,
            SetOperation(SetOps.EQUALS, item_type),
        )


    def _ensure_map_typing(self, kv_type: object) -> tuple[PType, PType]:
        if isinstance(kv_type, list):
            assert len(kv_type) == 2
            kv_type = (kv_type[0], kv_type[1])
        return kv_type


    def map_new(self, kv_type: tuple[PType, PType]) -> Readable:
        return Readable(
            MapOperation(MapOps.NEW, self._ensure_map_typing(kv_type)),
        )


    def map_get(self, kv_type: tuple[PType, PType], map_ref: Readable, key: Readable) -> Readable:
        return Readable(
            *map_ref.instructions,
            *key.instructions,
            MapOperation(MapOps.GET, self._ensure_map_typing(kv_type)),
        )


    def map_set(self, kv_type: tuple[PType, PType], map_ref: Readable, key: Readable, value: Readable) -> None:
        self._add_instructions(
            *map_ref.instructions,
            *key.instructions,
            *value.instructions,
            MapOperation(MapOps.SET, self._ensure_map_typing(kv_type)),
        )


    def map_remove(self, kv_type: tuple[PType, PType], map_ref: Readable, key: Readable) -> None:
        self._add_instructions(
            *map_ref.instructions,
            *key.instructions,
            MapOperation(MapOps.REMOVE, self._ensure_map_typing(kv_type)),
        )


    def map_has_key(self, kv_type: tuple[PType, PType], map_ref: Readable, key: Readable) -> Readable:
        return Readable(
            *map_ref.instructions,
            *key.instructions,
            MapOperation(MapOps.HAS_KEY, self._ensure_map_typing(kv_type)),
        )


    def map_has_value(self, kv_type: tuple[PType, PType], map_ref: Readable, value: Readable) -> Readable:
        return Readable(
            *map_ref.instructions,
            *value.instructions,
            MapOperation(MapOps.HAS_VALUE, self._ensure_map_typing(kv_type)),
        )


    def map_has_pair(self, kv_type: tuple[PType, PType], map_ref: Readable, key: Readable, value: Readable) -> Readable:
        return Readable(
            *map_ref.instructions,
            *key.instructions,
            *value.instructions,
            MapOperation(MapOps.HAS_PAIR, self._ensure_map_typing(kv_type)),
        )


    def map_any_key(self, kv_type: tuple[PType, PType], map_ref: Readable) -> Readable:
        return Readable(
            *map_ref.instructions,
            MapOperation(MapOps.ANY_KEY, self._ensure_map_typing(kv_type)),
        )


    def map_any_value(self, kv_type: tuple[PType, PType], map_ref: Readable) -> Readable:
        return Readable(
            *map_ref.instructions,
            MapOperation(MapOps.ANY_VALUE, self._ensure_map_typing(kv_type)),
        )


    def map_union(self, kv_type: tuple[PType, PType], in_a: Readable, in_b: Readable, out: Readable) -> None:
        self._add_instructions(
            *in_a.instructions,
            *in_b.instructions,
            *out.instructions,
            MapOperation(MapOps.UNION, self._ensure_map_typing(kv_type)),
        )


    def map_intersection(self, kv_type: tuple[PType, PType], in_a: Readable, in_b: Readable, out: Readable) -> None:
        self._add_instructions(
            *in_a.instructions,
            *in_b.instructions,
            *out.instructions,
            MapOperation(MapOps.INTERSECTION, self._ensure_map_typing(kv_type)),
        )


    def map_equals(self, kv_type: tuple[PType, PType], a: Readable, b: Readable) -> Readable:
        return Readable(
            *a.instructions,
            *b.instructions,
            MapOperation(MapOps.EQUALS, self._ensure_map_typing(kv_type)),
        )

    def transform_new(self, kv_type: tuple[PType, PType]) -> Readable:
        return Readable(
            TransformOperation(TransformOps.NEW, self._ensure_map_typing(kv_type)),
        )


    def transform_get(self, kv_type: tuple[PType, PType], transform_ref: Readable, key: Readable) -> Readable:
        return Readable(
            *transform_ref.instructions,
            *key.instructions,
            TransformOperation(TransformOps.GET, self._ensure_map_typing(kv_type)),
        )


    def transform_set(self, kv_type: tuple[PType, PType], transform_ref: Readable, key: Readable, value: Readable) -> None:
        self._add_instructions(
            *transform_ref.instructions,
            *key.instructions,
            *value.instructions,
            TransformOperation(TransformOps.SET, self._ensure_map_typing(kv_type)),
        )


    def call(self,
             function_or_method: str | tuple[str, str], args: list[Readable],
             return_type: PType | None,
             *,
             discard_result: bool = False,
             virtual: bool = True,
    ) -> Readable | None:
        discard_result &= return_type is not None
        for arg in args:
            self._add_instructions(*arg.instructions,)

        call = None
        argc = len(args)

        if isinstance(function_or_method, str):
            # a static call
            call = CallStatic(function_or_method, argc)
        else:
            # a virtual call?
            clazz, method = function_or_method
            if virtual:
                call = CallVirtual(clazz, method, argc)
            else:
                call = CallStatic(structure_member_to_signature(clazz, method), argc)

        if not self._ignore_followup_instructions:
            self._current_block.next = call
            self._current_block = call.next = BasicBlock()

        if discard_result:
            self._add_instructions(Pop())
            return None
        else:
            if return_type is None:
                return None
            else:
                result_handle = self.make_local_variable(return_type)
                self.write(result_handle.w, Readable())  # store the 'flying' result
                return result_handle.r


    def _push_loop_id(self, id: object) -> None:
        self._loop_id_stack.append(id)


    def _pop_loop_id(self) -> None:
        self._loop_id_stack.pop()


    def _get_current_loop_id(self) -> object:
        return self._loop_id_stack[-1]


    def begin_if(self, condition: BranchCallbackWithResult):
        assert condition is not None

        class IfBuilder(GraphJunctionBuilder):
            def __init__(self, ctx: CompilerContext) -> None:
                self._ctx = ctx
                self._then: BranchCallback | None = None
                self._else: BranchCallback | None = None
                ctx._incomplete_builders.append(self)

            def then(self, action: BranchCallback):
                assert action is not None
                self._then = action
                return self

            def otherwise(self, action: BranchCallback):
                assert action is not None
                self._else = action
                return self

            def end_if(self) -> None:
                cc = self._ctx
                cc._incomplete_builders.remove(self)
                assert self._then is not None
                if cc._ignore_followup_instructions:
                    return

                switch = cc._current_block.next = Switch(None)

                # 'executing' the condition
                switch.value_source = cc._current_block = BasicBlock()
                cc._current_block.instructions.extend(condition().instructions)
                cc._ignore_followup_instructions = False

                # 'running' along the 'THEN' branch
                then_entry = cc._current_block = BasicBlock()
                self._then()
                cc._ignore_followup_instructions = False
                switch.cases.append((
                    BasicBlock(),
                    then_entry
                ))

                # 'running' along the 'ELSE' branch
                else_entry = cc._current_block = BasicBlock()
                if self._else is not None:
                    self._else()
                cc._ignore_followup_instructions = False
                switch.cases.append((
                    BasicBlock([
                        PrimitiveOp(PrimitiveOps.NOT),
                    ]),
                    else_entry
                ))

                # continue the execution, even if there is an empty dangling block after the last 'if'
                cc._current_block = switch.next = BasicBlock()

        return IfBuilder(self)


    def begin_loop(self, condition: BranchCallbackWithResult):
        assert condition is not None

        class LoopBuilder(GraphJunctionBuilder):
            def __init__(self, ctx: CompilerContext) -> None:
                self._ctx = ctx
                self._body: BranchCallback | None = None
                ctx._incomplete_builders.append(self)

            def body(self, action: BranchCallback):
                assert action is not None
                self._body = action
                return self

            def end_loop(self) -> None:
                cc = self._ctx
                cc._incomplete_builders.remove(self)
                assert self._body is not None
                if cc._ignore_followup_instructions:
                    return

                last_block = cc._current_block

                # 'executing' the condition
                cond = cc._current_block = BasicBlock()
                cc._current_block.instructions.extend(condition().instructions)
                cc._ignore_followup_instructions = False

                # 'running' along the True branch (i.e. the main body of the loop)
                body = cc._current_block = BasicBlock()
                loop_id = cc._next_loop_id()
                loop_node = last_block.next = While(loop_id, cond, body)
                cc._push_loop_id(loop_id)
                self._body()
                cc._pop_loop_id()
                cc._ignore_followup_instructions = False

                # continue the execution, even if there is an empty dangling block after the last 'while'
                cc._current_block = loop_node.next = BasicBlock()

        return LoopBuilder(self)


    def loop_break(self) -> None:
        if not self._ignore_followup_instructions:
            node = self._current_block.next = Break(self._get_current_loop_id())
            self._current_block = node
            self._ignore_followup_instructions = True


    def loop_continue(self) -> None:
        if not self._ignore_followup_instructions:
            node = self._current_block.next = Continue(self._get_current_loop_id())
            self._current_block = node
            self._ignore_followup_instructions = True


    def end_of_program(self) -> None:
        if not self._ignore_followup_instructions:
            node = self._current_block.next = EndOfProgram()
            self._current_block = node
            self._ignore_followup_instructions = True


    def field_read(self, instance_ref: Readable, structure_name: str, field_name: str) -> Readable:
        return Readable(
            *instance_ref.instructions,
            FieldRead(structure_name, field_name),
        )


    def field_write(self, instance_ref: Readable, structure_name: str, field_name: str, value: Readable) -> None:
        self._add_instructions(
            *instance_ref.instructions,
            *value.instructions,
            FieldWrite(structure_name, field_name),
        )


    def instance_of(self, ref: Readable, structure_name: str, *, exact_match: bool = False) -> Readable:
        return Readable(
            *ref.instructions,
            InstanceOf(structure_name, exact=exact_match),
        )


    def new_instance(self, structure_name: str, constructor: str | None = None, args: list[Readable] = None) -> Readable:
        self._add_instructions(
            NewInstance(structure_name),
        )
        if constructor is not None:
            assert args is not None
            self._add_instructions(
                Copy(),
            )
            self.call((structure_name, constructor), args, None, virtual=False)
        return Readable()


    # TODO: is this really needed?
    def free_instance(self, ref: Readable, destructor: str | tuple[str, str] | None = None) -> None:
        self._add_instructions(
            *ref.instructions,
        )
        if destructor is not None:
            self._add_instructions(
                Copy(),
            )
            self.call(destructor, [], None, virtual=isinstance(destructor, tuple))
        self._add_instructions(
            FreeInstance(),
        )


    def simple_diff(self, result_type: PType, condition_same: Readable) -> Readable:
        return Readable(
            *condition_same.instructions,
            SimpleDiff(result_type),
        )


    def abs(self, value: Readable) -> Readable:
        return Readable(
            *value.instructions,
            PrimitiveOp(PrimitiveOps.ABS),
        )


    def min(self, a: Readable, b: Readable) -> Readable:
        return Readable(
            *a.instructions,
            *b.instructions,
            PrimitiveOp(PrimitiveOps.MIN),
        )


    def max(self, a: Readable, b: Readable) -> Readable:
        return Readable(
            *a.instructions,
            *b.instructions,
            PrimitiveOp(PrimitiveOps.MAX),
        )


    def distinct_values(self, values: list[Readable]) -> Readable:
        instructions: list[Instruction] = []
        for v in values:
            instructions.extend(v.instructions)
        return Readable(
            *instructions,
            DistinctValues(len(values)),
        )


    def get_fault_status(self) -> Readable:
        return Readable(
            FaultStatusRead(),
        )


    # TODO: is this really needed?
    def clear_fault_status(self) -> None:
        self._add_instructions(
            FaultStatusClear(),
        )


    def try_block(self, body: BranchCallback):
        assert body is not None

        class TryBuilder(GraphJunctionBuilder):
            def __init__(self, ctx: CompilerContext, body: BranchCallback):
                self._ctx = ctx
                self._body = body
                self._catch_handlers: dict[str, Callable[[JoinedHandle], None]] = {}
                self._finally_handler = None
                ctx._incomplete_builders.append(self)

            def catch(self, error_structure_type: str, handler: Callable[[JoinedHandle], None]):
                assert error_structure_type and error_structure_type != EXCEPTION_MATCHER_ALL
                assert handler is not None
                self._catch_handlers[error_structure_type] = handler
                return self

            def final(self, handler: BranchCallback):
                assert handler is not None
                self._finally_handler = handler
                return self


            def explore(self) -> None:
                cc = self._ctx
                cc._incomplete_builders.remove(self)
                assert len(self._catch_handlers) > 0 or self._finally_handler is not None
                if cc._ignore_followup_instructions:
                    return

                last_block = cc._current_block

                # 'running' along the main body
                body = cc._current_block = BasicBlock()
                try_node = last_block.next = TryBlock(body)
                self._body()
                cc._ignore_followup_instructions = False

                # 'running' along each catch-handler in the specified order
                for structure_name, handler in self._catch_handlers.items():
                    handler_entry = cc._current_block = BasicBlock()
                    exception = cc.make_local_variable(reference)
                    # pushing the 'flying' error value into a variable
                    cc.write(exception.w, Readable(
                        ExceptionRead(),
                    ))
                    cc._add_instructions(
                        PushPrimitive(0, reference),
                        ExceptionWrite(),
                    )
                    #
                    handler(exception)
                    #
                    cc._ignore_followup_instructions = False
                    try_node.catch_handlers[structure_name] = handler_entry

                # 'running' along the 'finally' section
                if self._finally_handler is not None:
                    try_node.finishing_section = cc._current_block = BasicBlock()
                    exception = cc.make_local_variable(reference)
                    # pushing the 'flying' error value into a variable
                    cc.write(exception.w, Readable(
                        ExceptionRead(),
                    ))
                    cc._add_instructions(
                        PushPrimitive(0, reference),
                        ExceptionWrite(),
                    )
                    #
                    self._finally_handler()
                    #
                    cc.begin_if(lambda: (
                        exception.r != cc.null_ref
                    )).then(lambda: (
                        cc.throw(exception.r),  # automatically re-throwing the exception if there is one
                    )).end_if()
                    cc._ignore_followup_instructions = False

                # continue the execution, even if there is an empty dangling block after this one
                cc._current_block = try_node.next = BasicBlock()


        return TryBuilder(self, body)


    def throw(self, value: Readable) -> None:
        if not self._ignore_followup_instructions:
            self._add_instructions(
                *value.instructions,
                ExceptionWrite(),
            )
            node = self._current_block.next = Throw()
            self._current_block = node
            self._ignore_followup_instructions = True


    def floor(self, value: Readable) -> Readable:
        return Readable(
            *value.instructions,
            PrimitiveOp(PrimitiveOps.FLOOR),
        )


    def get_string_length(self, s: Readable) -> Readable:
        return Readable(
            *s.instructions,
            StringOperation(StringOps.LENGTH),
        )


    def concat_strings(self, str_a: Readable, str_b: Readable) -> Readable:
        return Readable(
            *str_a.instructions,
            *str_b.instructions,
            StringOperation(StringOps.CONCAT),
        )


    def string_contains(self, s: Readable, substr: Readable) -> Readable:
        return Readable(
            *s.instructions,
            *substr.instructions,
            StringOperation(StringOps.CONTAINS),
        )


    def string_index_of(self, s: Readable, sub: Readable, offset: Readable) -> Readable:
        return Readable(
            *s.instructions,
            *sub.instructions,
            *offset.instructions,
            StringOperation(StringOps.INDEX_OF),
        )


    def string_last_index_of(self, s: Readable, sub: Readable) -> Readable:
        return Readable(
            *s.instructions,
            *sub.instructions,
            StringOperation(StringOps.LAST_INDEX_OF),
        )


    def string_starts_with(self, s: Readable, prefix: Readable) -> Readable:
        return Readable(
            *s.instructions,
            *prefix.instructions,
            StringOperation(StringOps.STARTS_WITH),
        )


    def string_ends_with(self, s: Readable, suffix: Readable) -> Readable:
        return Readable(
            *s.instructions,
            *suffix.instructions,
            StringOperation(StringOps.ENDS_WITH),
        )


    def string_copy(self, s: Readable, offset: Readable, count: Readable) -> Readable:
        return Readable(
            *s.instructions,
            *offset.instructions,
            *count.instructions,
            StringOperation(StringOps.COPY),
        )


    def string_length(self, s: Readable, old: Readable, new: Readable) -> Readable:
        return Readable(
            *s.instructions,
            *old.instructions,
            *new.instructions,
            StringOperation(StringOps.REPLACE_ONCE),
        )


    def string_to_integer(self, value: Readable) -> Readable:
        return Readable(
            *value.instructions,
            StringOperation(StringOps.STR_TO_INT),
        )


    def integer_to_string(self, value: Readable) -> Readable:
        return Readable(
            *value.instructions,
            StringOperation(StringOps.INT_TO_STR),
        )


    def string_ord(self, s: Readable) -> Readable:
        return Readable(
            *s.instructions,
            StringOperation(StringOps.ORD),
        )


    def begin_switch(self, value_type: PType, value: BranchCallbackWithResult):
        assert value_type.is_primitive()
        assert value is not None

        class SwitchBuilder(GraphJunctionBuilder):
            def __init__(self, ctx: CompilerContext):
                ctx._incomplete_builders.append(self)
                self._ctx = ctx
                self._cases: dict[ValueType, BranchCallback] = {}
                self._default_handler: BranchCallback | None = None

            def when(self, value: ValueType, handler: BranchCallback):
                assert value is not None
                assert handler is not None
                self._cases[value] = handler
                return self

            def otherwise(self, wildcard_handler: BranchCallback):
                assert wildcard_handler is not None
                self._default_handler = wildcard_handler
                return self

            def end_switch(self) -> None:
                cc = self._ctx
                cc._incomplete_builders.remove(self)
                if cc._ignore_followup_instructions:
                    return

                # constructing the branching node
                switch = cc._current_block.next = Switch(None)

                # 'running' value source branch
                switch.value_source = cc._current_block = BasicBlock()
                cc._current_block.instructions.extend(value().instructions)
                cc._ignore_followup_instructions = False

                # 'running' individual branches
                for condition_value, handler in self._cases.items():
                    condition = BasicBlock()
                    condition.instructions.extend([
                        PushPrimitive(condition_value, value_type),
                        PrimitiveOp(PrimitiveOps.EQ),
                    ])
                    # ===
                    handler_entry = cc._current_block = BasicBlock()
                    handler()
                    cc._ignore_followup_instructions = False
                    # ===
                    switch.cases.append((
                        condition,
                        handler_entry
                    ))

                # always adding a wildcard handler
                condition = BasicBlock()
                condition.instructions.extend([
                    PushPrimitive(condition_value, value_type)
                    for condition_value in self._cases.keys()
                ])
                condition.instructions.append(
                    DistinctValues(len(self._cases) + 1)  # unmatched cases + source
                )
                # ===
                handler_entry = cc._current_block = BasicBlock()
                if self._default_handler is not None:
                    self._default_handler()
                cc._ignore_followup_instructions = False
                # ===
                switch.cases.append((
                    condition,
                    handler_entry
                ))

                # continuation after the switch
                cc._current_block = switch.next = BasicBlock()

        return SwitchBuilder(self)


    def is_array(self, ref: Readable, item_type: PType) -> Readable:
        assert item_type.is_primitive()
        return Readable(
            *ref.instructions,
            ContainerTypeCheck(ContainerKind.ARRAY, [item_type]),
        )


    def is_set(self, ref: Readable, item_type: PType) -> Readable:
        assert item_type.is_primitive()
        return Readable(
            *ref.instructions,
            ContainerTypeCheck(ContainerKind.SET, [item_type]),
        )


    def is_map(self, ref: Readable, key_type: PType, value_type: PType) -> Readable:
        assert key_type.is_primitive()
        assert value_type.is_primitive()
        return Readable(
            *ref.instructions,
            ContainerTypeCheck(ContainerKind.MAP, [key_type, value_type]),
        )


    def is_transform(self, ref: Readable, key_type: PType, value_type: PType) -> Readable:
        assert key_type.is_primitive()
        assert value_type.is_primitive()
        return Readable(
            *ref.instructions,
            ContainerTypeCheck(ContainerKind.TRANSFORM, [key_type, value_type]),
        )


