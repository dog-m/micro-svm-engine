from typing import Callable, cast

from .compiler import CompilerContext, Readable
from .decoding import StateIntermediateDescription, VariableSource
from .descriptors import VariableInfo
from .execution import SymbolicStateMachine, SymRefPolicy
from .exploration import PathEnumerator, Program, ProgramPath
from .global_context import GlobalContext
from .instructions import (
    Assume,
    ContainerGetSize,
    DistinctValues,
    Instruction,
    PrimitiveOp,
    PrimitiveOps,
    PushPrimitive,
    VariableRead,
)
from .state import ObjectState, ProgramState, VariableState
from .type_hierarchy import TypeHierarchyResolver
from .types import (
    ArrayTypeInfo,
    InitializerValueType,
    MapTypeInfo,
    SetTypeInfo,
    StructureTypeInfo,
    TransformTypeInfo,
    TypeInfo,
    ValueType,
    boolean,
    integer,
    reference,
)


class RefIdGenerator:
    def __init__(self):
        self._mapping: dict[int, str] = {}

    def get(self, ref: int) -> str | None:
        if ref == 0:
            result = None
        elif ref in self._mapping:
            result = self._mapping[ref]
        else:
            result = self._mapping[ref] = f"#{len(self._mapping):03x}"
        return result



class ReferenceHandlePool:
    def __init__(self, ctx: GlobalContext):
        self.items: list[VariableInfo] = []
        self.last = -1
        self.ctx = ctx

    def get(self) -> VariableInfo:
        self.last += 1
        if self.last >= len(self.items):
            v = VariableInfo(f"ref-handle-pool${self.last}", reference)
            self.ctx.register_symbol(v)
            self.items.append(v)
        return self.items[self.last]

    def reset(self) -> None:
        self.last = -1



class DetectedFailure:
    def __init__(self, fname: str, failure_id):
        self.function_name = fname
        self.failure_id = failure_id
        self.call_args: list[ValueType] = []
        self.program_state = ProgramState()

    def _render_arg(self, arg: ValueType, type: TypeInfo) -> str:
        if type.is_reference():
            assert isinstance(arg, str)
            return arg
        else:
            return repr(arg)

    def as_string(self, ctx: GlobalContext) -> str:
        func = ctx.functions[self.function_name]
        args = [
            self._render_arg(self.call_args[i], ptype)
            for i, ptype in enumerate(func.parameters.values())
        ]
        if func.is_static:
            return f"{func.full_name}({', '.join(args)})"
        else:
            return f"{args[0]}.{func.original_name}({', '.join(args[1:])})"



SOLUTION_TAG = '#solution'
SOLUTION_TAGS = { SOLUTION_TAG, }


class DefectAnalyzerConfig:
    def __init__(self):
        self.max_collection_size   = 50
        self.solver_try_count      = 21
        self.timeout               = 2.1 * 1000
        self.loop_max_iter_count   = 17
        self.loop_reduction_factor = 10.0
        self.branching_budget      = 10



class DefectAnalyzer:
    def __init__(self, context: GlobalContext):
        self.spec = context
        self.th_resolver = TypeHierarchyResolver(context)
        self.th_resolver.analyze_structure_hierarchy()
        self.on_defect: Callable[[DetectedFailure], None] | None = None
        self.defects_found = 0
        self.config = DefectAnalyzerConfig()
        self.size_type = integer


    def _refine_solution(
            self,
            argument_variables: list[VariableInfo],
            state: StateIntermediateDescription,
            solution: DetectedFailure,
        ) -> None:
        id_generator = RefIdGenerator()

        queue: list[tuple[str, int]] = []
        def schedule(id: str, ref: int) -> None:
            if ref != 0:
                queue.append((id, ref))

        def prepare_variable(variable: VariableInfo) -> InitializerValueType:
            type = variable.type
            value = state.get_value(variable.name)
            if type.is_reference():
                id = id_generator.get(value)
                schedule(id, value)
                return id
            else:
                return value

        for variable in argument_variables:
            value = prepare_variable(variable)
            solution.call_args.append(value)

        for variable in self.spec.global_variables.values():
            value = prepare_variable(variable)
            solution.program_state.global_variables[variable.name] = VariableState(
                variable.name,
                value
            )

        visited: set[str] = set()
        while queue:
            obj_id, ref = queue.pop()
            if obj_id not in visited:
                visited.add(obj_id)

                type = state.reachability_map[ref].type
                value = state.get_value(ref)

                if isinstance(type, StructureTypeInfo):
                    value = cast(dict[str, tuple[ValueType, TypeInfo]], value)
                    for fname, (fvalue, ftype) in value.items():
                        if ftype.is_reference():
                            id = id_generator.get(fvalue)
                            schedule(id, fvalue)
                            value[fname] = id
                        else:
                            value[fname] = fvalue

                elif isinstance(type, (ArrayTypeInfo, SetTypeInfo)):
                    value = cast(list[ValueType], value)
                    if type.item_type.is_reference():
                        for i, v in enumerate(value):
                            id = id_generator.get(v)
                            schedule(id, v)
                            value[i] = id

                elif isinstance(type, (MapTypeInfo, TransformTypeInfo)):
                    value  = cast(list[tuple[ValueType, ValueType]], value)
                    rkey   = type.key_type.is_reference()
                    rvalue = type.value_type.is_reference()
                    if rkey or rvalue:
                        for i, (k, v) in enumerate(value):
                            if rkey:
                                id = id_generator.get(k)
                                schedule(id, k)
                                k = id
                            if rvalue:
                                id = id_generator.get(v)
                                schedule(id, v)
                                v = id
                            value[i] = (k, v)

                else:
                    raise AssertionError(f"Unexpected type: {type}")

                solution.program_state.objects[obj_id] = ObjectState(obj_id, type, value)

        # attach mandatory objects
        for i, variable in enumerate(argument_variables):
            if variable.type.is_reference():
                id = solution.call_args[i]
                obj = solution.program_state.objects[id]
                solution.program_state.expected_objects[id] = obj


    def _tactic_object_count(self, state: StateIntermediateDescription, ref_handles: dict[int, VariableRead]):
        if state.structure_count <= 1:
            return None

        res: list[Instruction] = []
        # tactic: reduce the number of *objects* by stating that there are less distinct references exist than currently are
        for ref in ref_handles.keys():
            if not state.is_container(ref):
                res.append(ref_handles[ref])
        res.extend([
            DistinctValues(state.structure_count),
            PrimitiveOp(PrimitiveOps.NOT),
            Assume(),
        ])
        return res


    def _tactic_collection_sizes(self, state: StateIntermediateDescription, ref_handles: dict[int, VariableRead]):
        if state.collection_count == 0:
            return None

        res: list[Instruction] = [PushPrimitive(False, boolean)]
        empty_containers: list[VariableRead] = []
        # tactic: reduce the number of *elements* in containers by stating new container sizes
        for ref, src in ref_handles.items():
            if state.is_container(ref) and not isinstance(state.reachability_map[ref].type, TransformTypeInfo):
                size_old = state.collection_sizes[ref]
                if size_old == 0:
                    empty_containers.append(src)

                elif size_old > 0:
                    res.extend([
                        src,
                        ContainerGetSize(),
                    ])
                    if size_old == 1:
                        res.extend([
                            PushPrimitive(0, self.size_type),
                            PrimitiveOp(PrimitiveOps.EQ),
                        ])
                    else:
                        res.extend([
                            PushPrimitive(size_old, self.size_type),
                            PrimitiveOp(PrimitiveOps.LESS),
                        ])
                    res.append(
                        PrimitiveOp(PrimitiveOps.OR)
                    )
        # i.e. "assume(False or (len(c1) < N) or (len(c2) < M) or (len(c3) == 0) or ...)"
        res.append(Assume())

        # 2 instructions = no non-empty containers were found
        if len(empty_containers) == state.collection_count:
            res.clear()  # remove "assume(False)"

        # enforce empty containers to remain empty
        for src in empty_containers:
            # i.e. "assume(len(c) == 0)" for every empty container reference
            res.extend([
                src,
                ContainerGetSize(),
                PushPrimitive(0, self.size_type),
                PrimitiveOp(PrimitiveOps.EQ),
                Assume(),
            ])

        return res


    def _optimize_solution(
            self,
            argument_variables: list[VariableInfo],
            path: ProgramPath,
            m: SymbolicStateMachine,
            cache: dict[object, bool],
        ) -> StateIntermediateDescription:
        ref_pool = ReferenceHandlePool(self.spec)
        reduction_tactics = [
            self._tactic_object_count,
            self._tactic_collection_sizes,
        ]

        max_collection_size = self.config.max_collection_size
        state = None
        while state is None:
            print('[i] Decoding state...', flush=True)
            state = StateIntermediateDescription.analyze(m, argument_variables, self.th_resolver, self.spec)

            # ===========================
            print('[~] Structures:', state.structure_count)
            max_collection_size = max(state.collection_sizes.values(), default=0)
            print('[~] Collections:', state.collection_count, f"(max size = {max_collection_size})")
            #print('[~] reachability_map:')
            #for ref, rinfo in state.reachability_map.items():
            #    print(ref, ':', rinfo.type, 'from', rinfo.sources)
            # ===========================

            # grounding the references
            ref_pool.reset()
            ref_handles: dict[int, VariableRead] = {}
            for ref, rinfo in state.reachability_map.items():
                grounding = rinfo.get_grounding()
                if grounding is None:
                    grounding = VariableSource(ref_pool.get().name, is_local=True)
                ref_handles[ref] = cast(VariableRead, grounding.to_instructions(ref_handles)[0])

            instructions: list[Instruction] = []
            # connecting the references
            for ref, rinfo in state.reachability_map.items():
                handle_read = ref_handles[ref]
                for source in rinfo.sources:
                    instructions.extend([
                        *source.to_instructions(ref_handles),
                        handle_read,
                        PrimitiveOp(PrimitiveOps.EQ),
                        Assume(),
                    ])

            # applying reduction tactics
            for i, tactic in enumerate(reduction_tactics, start=1):
                adjustments = tactic(state, ref_handles)
                if adjustments is None:
                    continue

                # trying to execute the chosen tactic
                m = SymbolicStateMachine(
                    self.spec,
                    self.th_resolver,
                    check_cache=cache,
                    solver_timeout=self.config.timeout * 1.1
                )

                m.config.symbolic_ref_policy = SymRefPolicy.OPEN
                m.config.allow_type_unions = False
                m.config.solver_try_count = self.config.solver_try_count
                m.set_current_container_size_limit(max_collection_size)  # not allowing collections to grow

                m.play(path.instructions())
                m.flush_execution_stack()
                m.play(instructions)

                print(f"[i] Applying reduction tactic #{i}...", flush=True)
                if m.execute(adjustments):
                    state = None  # triggering re-evaluation
                    break

        return state


    def analyze_function(self, function_name: str) -> None:
        self.defects_found = 0

        func = self.spec.functions[function_name]
        cc = CompilerContext()
        args: list[Readable] = []
        for ptype in func.parameters.values():
            value = cc.make_local_variable(ptype, tags=SOLUTION_TAGS).r
            cc.assume(value == cc.symbolic(ptype))
            args.append(value)
        if not func.is_static:
            cc.assume(cc.instance_of(args[0], func.structure))
        discard_result = func.result_type is not None
        cc.call(func.full_name, args, func.result_type, virtual=False, discard_result=discard_result)
        cc.end_of_program()

        main = cc.build()
        for variable in main.local_variables:
            self.spec.register_symbol(variable)
        prog = Program(self.spec, main)

        failing_paths: list[tuple[ProgramPath, str | None]] = []

        def register_path(pp: ProgramPath, pe: PathEnumerator, meta: str | None, call_stack: list[str]) -> None:
            print('.', end='', flush=True)
            failing_paths.append((pp, meta))

        print(func)
        pe = PathEnumerator(prog, self.th_resolver)
        pe.config.loop_max_iter_count   = self.config.loop_max_iter_count
        pe.config.loop_reduction_factor = self.config.loop_reduction_factor
        pe.on_failing_path = register_path

        print('[i] Exploring', end='', flush=True)
        pe.explore(branching_budget=self.config.branching_budget)
        print(flush=True)

        print('[i] Found', len(failing_paths), 'potentially failing path(s).')
        cache = {}
        for path, failure_id in failing_paths:
            m = SymbolicStateMachine(
                self.spec,
                self.th_resolver,
                check_cache=cache,
                solver_timeout=self.config.timeout
            )

            m.config.symbolic_ref_policy = SymRefPolicy.OPEN
            m.config.allow_type_unions = False
            m.config.solver_try_count = self.config.solver_try_count
            m.set_current_container_size_limit(self.config.max_collection_size)

            if m.execute(path.instructions(), flush=True):
                self.defects_found += 1
                print('[!] Failure found:', failure_id)
                argument_variables = [v for v in main.local_variables if SOLUTION_TAG in v.tags]

                print('[i] Optimizing...')
                state = self._optimize_solution(argument_variables, path, m, cache)

                print('[i] Refining...')
                failure = DetectedFailure(function_name, failure_id)
                self._refine_solution(argument_variables, state, failure)

                if self.on_defect is not None:
                    self.on_defect(failure)

