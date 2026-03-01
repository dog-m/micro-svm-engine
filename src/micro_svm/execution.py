import os
from typing import Callable, Iterable, cast, final

import z3

from .descriptors import VariableInfo
from .global_context import GlobalContext
from .instructions import *  # noqa: F403
from .type_hierarchy import TypeHierarchyResolver
from .types import (
    PRIMITIVE_TYPES,
    ArrayTypeInfo,
    KnownReferenceTypeInfo,
    MapTypeInfo,
    SetTypeInfo,
    StructureTypeInfo,
    TransformTypeInfo,
    TypeInfo,
    array,
    boolean,
    integer,
    map_of,
    ref,
    reference,
    set_of,
    transform_of,
)

print(f"Z3 version: {z3.get_version_string()}")


@final
class VersionedVariable:
    def __init__(self, var: VariableInfo) -> None:
        self.variable = var
        self.version = 0

    def clone(self):
        vv = VersionedVariable(self.variable)
        vv.version = self.version
        return vv

    def increment(self):
        self.version += 1
        return self



@final
class VariableCache:
    def __init__(self) -> None:
        self.refs: dict[str, z3.ExprRef] = {}

    def _normalize(self, text: str) -> str:
        for c in '~!@#$%^&*()-+=/*[]{}\\|:;\'",.<>?':
            text = text.replace(c, '_')
        return text

    def _resolve_version(self, variable: VariableInfo, version: int) -> z3.ExprRef:
        full_name = f"{variable.name}:{version}"
        ref = self.refs.get(full_name)
        if ref is None:
            self.refs[full_name] = ref = z3.Const(full_name, variable.type.z3_sort)
        return ref

    def resolve(self, vv: VersionedVariable, version: int | None = None) -> z3.ExprRef:
        return self._resolve_version(vv.variable, vv.version if version is None else version)



@final
class SymbolicStateMachineStatistics:
    def __init__(self):
        # objects that were created(!) during 'execution'
        self.arrays: dict[int, PrimitiveTypeInfo] = {}
        self.sets: dict[int, PrimitiveTypeInfo] = {}
        self.maps: dict[int, tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]] = {}
        self.transforms: dict[int, tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]] = {}
        self.structures: dict[int, StructureTypeInfo] = {}


    def resolve_ref_type(self, reference: int | None) -> KnownReferenceTypeInfo | None:
        if reference is None:
            return None

        # TODO: avoid creating new objects here
        result = None
        if reference in self.arrays:
            result = array(self.arrays[reference])
        elif reference in self.sets:
            result = set_of(self.sets[reference])
        elif reference in self.maps:
            result = map_of(*self.maps[reference])
        elif reference in self.transforms:
            result = transform_of(*self.transforms[reference])
        elif reference in self.structures:
            result = self.structures[reference]
        else:
            return None

        return ref(result)




@final
class FaultMode(Enum):
    IGNORE = auto()
    AVOID  = auto()
    STORE  = auto()


@final
class SymRefPolicy(Enum):
    CLOSED = auto()
    OPEN   = auto()  # machine allowed to produce symbolic references to non-existing objects!


TRUE          = z3.BoolVal(True)
FALSE         = z3.BoolVal(False)
INVALID_SIZE  = -1


# for type id generation
_typeid_guid_type = integer


NULL_VALUE       = reference.default_value
NULL_TYPEID_NAME = '<null>'
NULL_TYPEID_SEQ  = z3.Unit(_typeid_guid_type.default_value)

def typeid_name_for_structure(name: str) -> str:
    return f"<type-id>{name}</type-id>"

def typeid_name_for_array(itype: TypeInfo) -> str:
    return f"array<{itype.name}>"

def typeid_name_for_set(itype: TypeInfo) -> str:
    return f"set<{itype.name}>"

def typeid_name_for_map(ktype: TypeInfo, vtype: TypeInfo) -> str:
    return f"map<{ktype.name},{vtype.name}>"

def typeid_name_for_transform(ktype: TypeInfo, vtype: TypeInfo) -> str:
    return f"transform<{ktype.name},{vtype.name}>"



@final
class MachineConfig:
    def __init__(self, solver_timeout: int | None):
        self.allow_type_unions = True
        self.fault_mode = FaultMode.AVOID
        self.solver_timeout = int(solver_timeout)
        self.solver_try_count = 10
        self.solver_tuning: dict[str, object] = {
            'qi.max_multi_patterns': 40,
            'rewrite_patterns': True,
            'threads': os.cpu_count() // 2,          # seems to be a decent approximation
            'threads.max_conflicts': 2_000_000_000,  # 400 by default
            #'unsat_core': True,                     # sometimes this causes false-negatives
            #'arith.random_initial_value': True,
            #'array.weak': True,
            #'compact': False,
            #'expand_select_ite': True,
            #'induction': True,
            #'propagate_eq': True,
        }
        self.symbolic_ref_policy = SymRefPolicy.CLOSED
        self.literal_substitution_enabled = True



@final
class SymbolicStateMachine:
    debug_unsat: bool = False
    debug_unknown: bool = False
    debug_dump_expressions: bool = False

    def __init__(self,
                 ctx: GlobalContext, th_resolver: TypeHierarchyResolver,
                 *,
                 check_cache: dict[object, bool] = None,
                 solver_timeout: int | None = None):
        self.context = ctx
        self.config = MachineConfig(solver_timeout)
        self.is_running = True
        self.statistics = SymbolicStateMachineStatistics()
        #
        self._is_initialized = False
        self._stack: list[object] = []  # WARNING: a general-purpose stack of items, there might be anything inside of it!
        self._stack_frame_number = 0
        self._instruction_resolver = InstructionResolver(self)
        self._expressions: list[z3.ExprRef] = []
        self._last_model: z3.ModelRef | None = None
        self._next_unique_id = 0
        self._variable_cache = VariableCache()
        self._versioned_symbols: dict[str, VersionedVariable] = {}
        self._check_cache = {} if check_cache is None else check_cache
        self._last_ref = 0
        self._typeid_seq_type = TypeInfo('micro-svm:type-id', z3.SeqSort(_typeid_guid_type.z3_sort), None)
        self._typeid_cache__to_sequence: dict[str, z3.SeqRef] = {}
        self._typeid_cache__to_name: dict[int, str] = {}
        self._array_pools: dict[str, VersionedVariable] = {}
        self._collection_sizes = VersionedVariable(VariableInfo('@collection-sizes', array(integer)))
        self._object_types = VersionedVariable(VariableInfo('@object-types', array(self._typeid_seq_type)))
        self._special_pools: dict[str, VersionedVariable] = {}
        self._th_resolver = th_resolver
        self._fault_flag = VersionedVariable(VariableInfo('@fault-flag', boolean))
        self._last_exception = VersionedVariable(VariableInfo('@last-exception', reference))
        # self._known_types = VersionedVariable(VariableInfo('@known-types', string))  # TODO: type unions
        self._last_literal_value: dict[str, z3.ExprRef] = {}  # variable -> last literal value


    # === [type id management] ==================================


    def _typeid_to_seq(self, id_name: str) -> z3.SeqRef:
        if (res := self._typeid_cache__to_sequence.get(id_name)) is None:
            # "NULL" is the "zero" one
            guid = len(self._typeid_cache__to_sequence) + 1
            res = z3.Unit(_typeid_guid_type.wrap_primitive(guid))

            self._typeid_cache__to_sequence[id_name] = res
            self._typeid_cache__to_name[guid]        = id_name

        return res


    def typeid_sequence_to_names(self, id_seq: z3.SeqRef) -> Iterable[str]:
        res: set[str] = set()

        for i in range(len(self._typeid_cache__to_name)):
            if z3.is_int_value(guid := z3.simplify(id_seq[i])):
                # there might be some non-existing GUIDs used by the solver
                if (name := self._typeid_cache__to_name.get(guid.as_long())) is not None:
                    res.add(name)
            else:
                break

        return res


    # === [initialization] ==================================

    def _init_symbols(self) -> None:
        if self._is_initialized:
            return
        self._is_initialized = True

        # prepare array lengths table and a table for retrieving simple object type info
        self._expressions.extend([
            self.array_get(self._object_types, NULL_VALUE) == NULL_TYPEID_SEQ,
            self.array_get(self._collection_sizes, NULL_VALUE) == INVALID_SIZE,
            self.read(self._fault_flag) == FALSE,
            self.read(self._last_exception) == NULL_VALUE,
        ])

        # create global pools for array 'allocation'
        for primitive in PRIMITIVE_TYPES:
            pool_name = self.get_array_pool_name_for(primitive)
            v = VariableInfo(pool_name, array(array(primitive)))
            vv = VersionedVariable(v)
            _ = self.read(vv)
            self._array_pools[pool_name] = vv

        # TODO: type unions
        # prepare all structure types
        # known_types: list[str] = []
        # for sinfo in self.context.structures.values():
        #     unified_id = self.get_unified_type_id_for(sinfo)
        #     known_types.append(unified_id)
        # self._expressions.append(
        #     self.read(self._known_types) == self._wrap_primitive('<type-separator>'.join(known_types), string)
        # )

        # other symbols from the provided context

        # prepare variables first
        variables: list[VersionedVariable] = []
        for v in self.context.global_variables.values():
            vv = self.to_versioned(v.name, is_local=False)
            _ = self.read(vv)
            variables.append(vv)

        # associate the values
        for vv in variables:
            v = vv.variable
            t = v.type

            if v.initializer is None:
                self._init_default(vv)

            else:
                value = v.initializer

                if isinstance(t, KnownReferenceTypeInfo):
                    self._init_reference(vv, value)
                elif isinstance(t, PrimitiveTypeInfo) and t.name != reference.name:
                    self._init_primitive(vv, value)
                else:
                    raise ValueError(f"Unsupported type initializer ({v})")


    def _init_default(self, vv: VersionedVariable) -> None:
        v = vv.variable
        if v.type.is_primitive() and v.type.default_value is not None:
            self._write_no_increment(vv, v.type.default_value)
        else:
            raise ValueError(f"Unable to default-initialize '{vv.variable}'")


    def _init_primitive(self, vv: VersionedVariable, value: object) -> None:
        self._write_no_increment(vv, self._wrap_primitive(value, vv.variable.type))


    def _init_reference(self, vv: VersionedVariable, value: object) -> None:
        t = cast(KnownReferenceTypeInfo, vv.variable.type).target_type

        if isinstance(t, ArrayTypeInfo):
            self._init_array_ref(vv, value)
        elif isinstance(t, SetTypeInfo):
            self._init_set_ref(vv, value, t)
        elif isinstance(t, MapTypeInfo):
            self._init_map_ref(vv, value, t)
        elif isinstance(t, TransformTypeInfo):
            self._init_transform_ref(vv, value, t)
        elif isinstance(t, StructureTypeInfo):
            self._init_object_ref(vv, value, t)
        else:
            raise ValueError(f"Unsupported reference type initializer ({vv.variable})")


    def _init_resolve_value(self, value: object | None, type: TypeInfo) -> z3.ExprRef:
        if type.is_reference():
            if value is None:
                return reference.default_value
            else:
                return self.read(self.to_versioned(value, is_local=False))
        else:
            return self._wrap_primitive(value, type)


    def _init_array_ref(self, vv: VersionedVariable, value: list[object]) -> None:
        t = cast(KnownReferenceTypeInfo, vv.variable.type).target_type
        t = cast(ArrayTypeInfo, t).item_type

        # allocate the array object and define its size first
        arr_ref = self.read(vv)
        self._expressions.extend([
            arr_ref == self.new_reference(),
            self.array_get(self._object_types, arr_ref) == self._typeid_to_seq(typeid_name_for_array(t)),
            self.array_get(self._collection_sizes, arr_ref) == len(value),
        ])

        # associate the values
        pool = self.get_array_ref_pools_for(t)[0]
        v_arr = self.array_get(pool, arr_ref)
        for i, x in enumerate(value):
            self._expressions.append(
                z3.Select(v_arr, i) == self._init_resolve_value(x, t)
            )


    def _init_set_ref(self, vv: VersionedVariable, value: list[object], set_type: SetTypeInfo) -> None:
        # allocate the set object and define its size first
        set_ref = self.read(vv)
        self._expressions.extend([
            set_ref == self.new_reference(),
            self.array_get(self._object_types, set_ref) == self._typeid_to_seq(typeid_name_for_set(set_type.item_type)),
            self.array_get(self._collection_sizes, set_ref) == len(value),
        ])

        # associate the values
        pool = self.get_set_pool_for(set_type.item_type)
        v_set = self.array_get(pool, set_ref)
        iv = self.read(self.make_temp_variable(set_type.item_type))

        if len(value) == 0:
            self._expressions.append(
                z3.ForAll(
                    [iv],
                    z3.Select(v_set, iv) == FALSE
                )
            )

        else:
            prepared_value: list[z3.ExprRef] = []
            for v in value:
                v = self._init_resolve_value(v, set_type.item_type)
                prepared_value.append(v)

            for v in prepared_value:
                tmp_value = self.read(self.make_temp_variable(set_type.item_type))
                self._expressions.extend([
                    #z3.And(
                        tmp_value == v,
                        z3.Select(v_set, tmp_value) == TRUE,
                    #),
                ])

            filters = [iv == v for v in prepared_value]
            filter_expr = z3.Or(*filters) if len(filters) > 1 else filters[0]

            self._expressions.extend([
                z3.ForAll(
                    [iv],
                    z3.If(  # no idea why this form works better
                        filter_expr,
                        z3.Select(v_set, iv) == TRUE,
                        z3.Select(v_set, iv) == FALSE,
                    )
                )
            ])


    def _init_map_ref(self, vv: VersionedVariable, value: dict[object, object], map_type: MapTypeInfo) -> None:
        # allocate the map object and define its size first
        map_ref = self.read(vv)
        self._expressions.extend([
            map_ref == self.new_reference(),
            self.array_get(self._object_types, map_ref) == self._typeid_to_seq(typeid_name_for_map(map_type.key_type, map_type.value_type)),
            self.array_get(self._collection_sizes, map_ref) == len(value),
        ])

        # associate the values
        pool = self.get_map_pool_for(map_type.kv_type)
        v_map = self.array_get(pool, map_ref)
        ik = self.read(self.make_temp_variable(map_type.key_type))
        iv = self.read(self.make_temp_variable(map_type.value_type))

        if len(value) == 0:
            self._expressions.append(
                z3.ForAll(
                    [ik, iv],
                    z3.Select(v_map, ik, iv) == FALSE
                )
            )

        else:
            prepared_value: list[tuple[z3.ExprRef, z3.ExprRef]] = []
            for k, v in value.items():
                k = self._init_resolve_value(k, map_type.key_type)
                v = self._init_resolve_value(v, map_type.value_type)
                prepared_value.append((k, v))

            for k, v in prepared_value:
                tmp_key   = self.read(self.make_temp_variable(map_type.key_type))
                tmp_value = self.read(self.make_temp_variable(map_type.value_type))
                self._expressions.extend([
                    #z3.And(
                        tmp_key   == k,
                        tmp_value == v,
                        z3.Select(v_map, tmp_key, tmp_value) == TRUE,
                    #),
                ])

            filters = [z3.And(ik == k, iv == v) for k, v in prepared_value]
            filter_expr = z3.Or(*filters) if len(filters) > 1 else filters[0]

            self._expressions.extend([
                z3.ForAll(
                    [ik, iv],
                    z3.If(  # no idea why this form works better
                        filter_expr,
                        z3.Select(v_map, ik, iv) == TRUE,
                        z3.Select(v_map, ik, iv) == FALSE,
                    )
                )
            ])


    def _init_transform_ref(self, vv: VersionedVariable, value: dict[object, object], type: TransformTypeInfo) -> None:
        # allocate the map object and define its size first
        transform_ref = self.read(vv)
        self._expressions.extend([
            transform_ref == self.new_reference(),
            self.array_get(self._object_types, transform_ref) == self._typeid_to_seq(typeid_name_for_transform(type.key_type, type.value_type)),
            self.array_get(self._collection_sizes, transform_ref) == len(value),
        ])

        # associate the values
        pool = self.get_transform_pool_for(type.kv_type)
        v_transform = self.array_get(pool, transform_ref)
        ik = self.read(self.make_temp_variable(type.key_type))

        if len(value) == 0:
            if type.value_type is boolean:
                self._expressions.append(
                    z3.ForAll(
                        [ik],
                        z3.Select(v_transform, ik) == type.value_type.default_value
                    )
                )
            # WARNING: it is too expensive to pre-fill other types!
        else:
            raise AssertionError('TODO?')


    def _init_object_ref(self, vv: VersionedVariable, value: dict[str, object], struct: StructureTypeInfo) -> None:
        # make a new instance
        obj_ref = self.read(vv)
        self._expressions.extend([
            obj_ref == self.new_reference(),
            self.array_get(self._object_types, obj_ref) == self.object_types_to_seq(self.get_type_names_for_object(struct)),
            self.array_get(self._collection_sizes, obj_ref) == INVALID_SIZE,
        ])

        # prepare/override default values for fields
        initializers = self.get_object_fields_initializer_for(struct.structure_name)
        for field, init_value in value.items():
            origin_class = self.get_object_field_origin(struct.structure_name, field)
            ftype = origin_class.fields[field].type
            initializers[field] = (self._init_resolve_value(init_value, ftype), origin_class)

        # set its field values
        self._expressions.extend([
            self.object_field_read(obj_ref, origin_class, field) == init
            for field, (init, origin_class) in initializers.items()
        ])

    # === [initialization] ==================================


    def set_current_container_size_limit(self, max_size: int) -> None:
        # NOTE: not sure why but having this here helps the solver
        self._init_symbols()

        sizes = self._collection_sizes
        type  = cast(ArrayTypeInfo, sizes.variable.type).item_type
        i_ref = self.read(self.make_temp_variable(reference))

        self._expressions.append(
            z3.ForAll(
                [i_ref],
                self.array_get(sizes, i_ref) <= self._wrap_primitive(max_size, type),
            )
        )


    def _wrap_primitive(self, value: object, type: TypeInfo) -> z3.ExprRef:
        return type.wrap_primitive(value)


    def _ensure_integer(self, value: z3.ExprRef | object) -> z3.ExprRef:
        if isinstance(value, z3.ExprRef) and value.sort_kind() == z3.Z3_BV_SORT:
            # WARNING: assuming all bit-vectors are signed!
            return z3.BV2Int(value, is_signed=True)
        else:
            return integer.z3_sort.cast(value)


    def _safeguard(self, *expectations: z3.ExprRef) -> None:
        match self.config.fault_mode:
            case FaultMode.IGNORE:
                pass  # doing nothing as expected

            case FaultMode.AVOID:
                self._expressions.extend(expectations)

            case FaultMode.STORE:
                self.write(
                    self._fault_flag,
                    z3.Or(self.read(self._fault_flag), *expectations)
                )

            case _:
                raise AssertionError(f"Unexpected fault mode: {self.config.fault_mode}")


    def push(self, value: object) -> None:
        self._stack.append(value)


    def pull(self, count: int = 1) -> object | list[object]:
        assert count > 0
        if count == 1:
            return self._stack.pop()  # more efficient
        res = self._stack[-count:]
        del self._stack[-count:]
        return res


    def check(self) -> None:
        if not self.is_running:
            return

        self.is_running = False
        self._last_model = None

        solver = z3.SolverFor('UF_ASLIA') #z3.Solver()

        for k, v in self.config.solver_tuning.items():
            solver.set(k, v)
        if self.config.solver_timeout is not None:
            solver.set('timeout', self.config.solver_timeout)
        if self.debug_unknown or self.debug_unsat:
            solver.set('smt.core.minimize', True)

        tracker_format = "@E{}"
        if False:
            # NOTE: tracking expressions appears to improve things a bit
            solver.assert_exprs(self._expressions)
        else:
            for (i, expr) in enumerate(self._expressions):
                try:
                    expr = self.simplify(expr)

                    if isinstance(expr, (z3.ExprRef, bool)):
                        if expr is True or z3.is_true(expr):
                            continue  # not sure if this improves things or not

                        if expr is False or z3.is_false(expr):
                            if self.debug_unsat:
                                print("[!] An expression has been simplified to pure 'FALSE' !!!")
                            # early termination, avoiding exceptions from the solver
                            return

                    solver.assert_and_track(expr, tracker_format.format(i))
                except Exception as e:
                    print("[!] PROBLEMATIC EXPRESSION:", expr, flush=True)
                    raise e

        res = None
        self._last_model = None
        for _ in range(self.config.solver_try_count):
            res = solver.check()
            solver.interrupt()
            self.is_running = (res == z3.sat)
            try:
                # NOTE: sometimes this is crashing for some reason
                self._last_model = None if not self.is_running else solver.model()
            except Exception:
                res = z3.unknown
                self.is_running = False
            if res != z3.unknown:
                break

        if not self.is_running:
            if self.debug_dump_expressions:
                print('---[expressions-start]---', flush=False)
                self.show_expressions()
                print('----[expressions-end]----', flush=True)

            match res:
                case z3.unsat:
                    if self.debug_unsat:
                        print('---[unsat-core-start]---', flush=False)
                        core = solver.unsat_core()
                        for i in range(len(self._expressions)):
                            if z3.Bool(tracker_format.format(i)) in core:
                                print(self._expressions[i], flush=False)
                        print('----[unsat-core-end]----', flush=True)

                case z3.unknown:
                    if self.debug_unknown:
                        reason = solver.reason_unknown()
                        if reason not in {'timeout', 'canceled'}:
                            print('\n!!! UNKNOWN !!!', 'reason:', reason, flush=True)


    def _control_check(self, id: object) -> bool | None:
        return self._check_cache.get(id)


    def _control_update(self, id: object, eval_result: bool) -> None:
        self._check_cache[id] = eval_result


    def _make_symbolic(self, type: PrimitiveTypeInfo) -> z3.ExprRef:
        v_value = z3.Const(f"#sym:{self._next_unique_id}", type.z3_sort)
        self._next_unique_id += 1

        if type.is_reference():
            self._expressions.append(v_value >= 0)
            if isinstance(type, KnownReferenceTypeInfo):
                tt = type.target_type
                guard: z3.ExprRef = None

                if isinstance(tt, StructureTypeInfo):
                    guard = self.object_is_instance_of(v_value, tt.structure_name, exact=False)
                elif tt.is_collection():
                    guard = self.array_get(self._collection_sizes, v_value) >= 0
                else:
                    raise AssertionError(f"Unsupported symbolic reference type: {type}")

                self._expressions.append((v_value == 0) | guard)
            if self.config.symbolic_ref_policy == SymRefPolicy.CLOSED:
                self._expressions.append(v_value <= self._last_ref)

        return v_value


    def simplify(self, expr: object | z3.ExprRef) -> z3.ExprRef:
        return z3.simplify(expr) if isinstance(expr, z3.ExprRef) else expr


    def to_versioned(
            self,
            original_name: str,
            *,
            is_local: bool = False,
            stack_frame: int | None = None,
        ) -> VersionedVariable:
        stack_frame = self._stack_frame_number if stack_frame is None else stack_frame
        name = f"(#{stack_frame}){original_name}" if is_local else original_name

        vv = self._versioned_symbols.get(name)
        if vv is None:
            v = self.context.get_symbol(original_name)
            if is_local:
                v = VariableInfo(name, v.type)
            vv = self._versioned_symbols[name] = VersionedVariable(v)
        return vv


    def read(self, var: VersionedVariable) -> z3.ExprRef:
        return self._variable_cache.resolve(var)


    def _write_no_increment(self, var: VersionedVariable, value: z3.ExprRef) -> None:
        self._expressions.append(
            self._variable_cache.resolve(var) == value
        )


    def write(self, var: VersionedVariable, value: z3.ExprRef) -> None:
        self._write_no_increment(var.increment(), value)


    def make_temp_variable(self, type: TypeInfo) -> VersionedVariable:
        v = VariableInfo(f"@tmp{self._next_unique_id}", type)
        vv = VersionedVariable(v)
        self._next_unique_id += 1
        return vv


    # === [pool management] =================================

    def get_array_pool_name_for(self, item_type: TypeInfo) -> str:
        return f"@arrays${item_type.name}"


    def get_array_ref_pools_for(self, item_type: TypeInfo | None) -> list[VersionedVariable]:
        if item_type is None:
            return self._array_pools.values()
        else:
            name = self.get_array_pool_name_for(item_type)
            pool = self._array_pools[name]
            return [pool]


    def get_set_pool_name_for(self, item_type: TypeInfo) -> str:
        return f"@sets${item_type.name}"


    def get_set_pool_for(self, item_type: TypeInfo) -> VersionedVariable:
        name = self.get_set_pool_name_for(item_type)
        pool = self._special_pools.get(name)
        if pool is None:
            v = VariableInfo(name, array(set_of(item_type)))
            pool = self._special_pools[name] = VersionedVariable(v)
        return pool


    def get_map_pool_name_for(self, kv_type: tuple[TypeInfo, TypeInfo]) -> VersionedVariable:
        return f"@maps${kv_type[0].name}+{kv_type[1].name}"


    def get_map_pool_for(self, kv_type: tuple[TypeInfo, TypeInfo]) -> VersionedVariable:
        name = self.get_map_pool_name_for(kv_type)
        pool = self._special_pools.get(name)
        if pool is None:
            v = VariableInfo(name, array(map_of(kv_type[0], kv_type[1])))
            pool = self._special_pools[name] = VersionedVariable(v)
        return pool


    def get_transform_pool_name_for(self, kv_type: tuple[TypeInfo, TypeInfo]) -> VersionedVariable:
        return f"@transforms${kv_type[0].name}+{kv_type[1].name}"


    def get_transform_pool_for(self, kv_type: tuple[TypeInfo, TypeInfo]) -> VersionedVariable:
        name = self.get_transform_pool_name_for(kv_type)
        pool = self._special_pools.get(name)
        if pool is None:
            v = VariableInfo(name, array(transform_of(kv_type[0], kv_type[1])))
            pool = self._special_pools[name] = VersionedVariable(v)
        return pool


    def get_object_field_pool_for(self, struct: StructureTypeInfo, field: str) -> VersionedVariable:
        name = f"@fields${struct.structure_name}.{field}"
        pool = self._special_pools.get(name)
        if pool is None:
            t = struct.fields[field].type
            v = VariableInfo(name, array(t))
            pool = self._special_pools[name] = VersionedVariable(v)
        return pool

    # === [pool management] =================================


    def array_get(self, src: VersionedVariable, index: z3.ExprRef) -> z3.ExprRef:
        index = self._ensure_integer(index)
        arr = self.read(src)
        return z3.Select(arr, index)


    def array_set(self, dst: VersionedVariable, index: z3.ExprRef, value: z3.ExprRef) -> None:
        index = self._ensure_integer(index)
        t = cast(ArrayTypeInfo, dst.variable.type).index_type
        v_iter = self.read(self.make_temp_variable(t))

        v_old = self.read(dst)
        v_new = self.read(dst.increment())

        self._expressions.extend([
            z3.ForAll(
                [v_iter],
                z3.Implies(
                    v_iter != index,
                    z3.Select(v_new, v_iter) == z3.Select(v_old, v_iter)
                )
            ),
            z3.Select(v_new, index) == value,
        ])


    def new_reference(self) -> z3.ExprRef:
        self._last_ref += 1
        return self._wrap_primitive(self._last_ref, reference)


    def advance_ref_counter(self, number_of_references: int) -> None:
        """
        This method might be useful for manually initializing N objects manually.
        """
        assert number_of_references >= 0
        self._last_ref += number_of_references


    def array_ref_init(self, dst: z3.ExprRef, size: z3.ExprRef, item_type: PrimitiveTypeInfo) -> None:
        self._expressions.extend([
            # specify the size and type
            self.array_get(self._object_types, dst) == self._typeid_to_seq(typeid_name_for_array(item_type)),
            self.array_get(self._collection_sizes, dst) == size,
        ])
        self._register_new_array(self._last_ref, item_type)


    def array_ref_get(self, src: z3.ExprRef, index: z3.ExprRef, type: PrimitiveTypeInfo) -> z3.ExprRef:
        index = self._ensure_integer(index)
        pool = self.get_array_ref_pools_for(type)[0]
        pool = self.read(pool)
        arr = z3.Select(pool, src)
        return z3.Select(arr, index)


    def array_ref_set(self, dst: z3.ExprRef, index: z3.ExprRef, value: z3.ExprRef, type: PrimitiveTypeInfo) -> None:
        index = self._ensure_integer(index)
        pool = self.get_array_ref_pools_for(type)[0]

        v_old     = self.read(pool)
        v_new     = self.read(pool.increment())
        v_old_arr = z3.Select(v_old, dst)
        v_new_arr = z3.Select(v_new, dst)

        t = cast(ArrayTypeInfo, pool.variable.type).index_type
        v_iter_outer = self.read(self.make_temp_variable(reference))
        v_iter_inner = self.read(self.make_temp_variable(t))

        self._expressions.extend([
            # 'moving' over the old arrays array-by-array
            z3.ForAll(
                [v_iter_outer],
                z3.Implies(
                    v_iter_outer != dst,
                    z3.Select(v_new, v_iter_outer) == z3.Select(v_old, v_iter_outer)
                )
            ),

            # 'copying' old elements of the modified array
            z3.ForAll(
                [v_iter_inner],
                z3.Implies(
                    v_iter_inner != index,
                    z3.Select(v_new_arr, v_iter_inner) == z3.Select(v_old_arr, v_iter_inner)
                )
            ),

            # 'changing' the element
            z3.Select(v_new_arr, index) == value,
        ])


    def array_ref_copy(self,
                       src: z3.ExprRef, src_index: z3.ExprRef,
                       dst: z3.ExprRef, dst_index: z3.ExprRef,
                       count: z3.ExprRef,
                       type: PrimitiveTypeInfo | None) -> None:
        src_index = self._ensure_integer(src_index)
        dst_index = self._ensure_integer(dst_index)
        for pool in self.get_array_ref_pools_for(type):
            v_old = self.read(pool)
            v_new = self.read(pool.increment())

            t = cast(ArrayTypeInfo, pool.variable.type).index_type
            v_index      = self.read(self.make_temp_variable(t))
            v_iter_outer = self.read(self.make_temp_variable(reference))

            v_src     = z3.Select(v_old, src)
            v_dst_old = z3.Select(v_old, dst)
            v_dst_new = z3.Select(v_new, dst)

            segment = z3.And(dst_index <= v_index, v_index < dst_index + count, count != 0)

            self._expressions.extend([
                # 'moving' over the old arrays array-by-array
                z3.ForAll(
                    [v_iter_outer],
                    z3.Implies(
                        v_iter_outer != dst,
                        z3.Select(v_new, v_iter_outer) == z3.Select(v_old, v_iter_outer)
                    )
                ),

                # copying the specified section
                z3.ForAll(
                    [v_index],
                    z3.And(
                        z3.Implies(
                            segment,
                            z3.Select(v_dst_new, v_index) == z3.Select(v_src, src_index + v_index - dst_index)
                        ),
                        z3.Implies(
                            z3.Not(segment),
                            z3.Select(v_dst_new, v_index) == z3.Select(v_dst_old, v_index)
                        ),
                        ## manual simplification from: (~segment) => ...
                        #z3.Or(
                        #    segment,
                        #    z3.Select(v_dst_new, v_index) == z3.Select(v_dst_old, v_index)
                        #),
                    )
                ),
            ])


    def array_ref_equals_range(self,
                               a: z3.ExprRef, a_offset: z3.ExprRef,
                               b: z3.ExprRef, b_offset: z3.ExprRef,
                               count: z3.ExprRef,
                               type: PrimitiveTypeInfo) -> z3.ExprRef:
        pool = self.get_array_ref_pools_for(type)[0]

        t = cast(ArrayTypeInfo, pool.variable.type).index_type
        index_iter: z3.ArithRef = self.read(self.make_temp_variable(t))

        pool = self.read(pool)
        a = z3.Select(pool, a)
        b = z3.Select(pool, b)
        output = self.read(self.make_temp_variable(boolean))

        self._expressions.extend([
            output == (
                z3.ForAll(
                    [index_iter],
                    z3.Implies(
                        z3.And(0 <= index_iter, index_iter < count, count != 0),
                        z3.Select(a, a_offset + index_iter) == z3.Select(b, b_offset + index_iter)
                    )
                )
            ),
        ])
        return output


    def set_ref_init(self, dst: z3.ExprRef, item_type: PrimitiveTypeInfo) -> None:
        pool  = self.read(self.get_set_pool_for(item_type))
        value = self.read(self.make_temp_variable(item_type))

        self._expressions.extend([
            # specify the size and type
            self.array_get(self._object_types, dst) == self._typeid_to_seq(typeid_name_for_set(item_type)),
            self.array_get(self._collection_sizes, dst) == 0,

            # make the initial assumption - there are no elements in this set
            z3.ForAll(
                [value],
                z3.Select(z3.Select(pool, dst), value) == FALSE
            ),
        ])
        self._register_new_set(self._last_ref, item_type)


    def set_ref_contains(self, src: z3.ExprRef, item: z3.ExprRef, item_type: PrimitiveTypeInfo) -> z3.ExprRef:
        pool    = self.read(self.get_set_pool_for(item_type))
        c_value = self.read(self.make_temp_variable(item_type))
        # no idea why but this works better for symbolic variables
        return z3.Exists(
            [c_value],
            z3.And(
                c_value == item,
                z3.Select(z3.Select(pool, src), c_value) == TRUE,
            )
        )


    def set_ref_get_any(self, src: z3.ExprRef, item_type: PrimitiveTypeInfo) -> z3.ExprRef:
        pool = self.read(self.get_set_pool_for(item_type))
        item = self.read(self.make_temp_variable(item_type))
        self._expressions.append(
            z3.Select(z3.Select(pool, src), item) == TRUE
        )
        return item


    def set_ref_add(self, dst: z3.ExprRef, item: z3.ExprRef, item_type: PrimitiveTypeInfo) -> None:
        pool  = self.get_set_pool_for(item_type)
        p_old = self.read(pool)
        p_new = self.read(pool.increment())

        has_item = self.read(self.make_temp_variable(boolean))
        c_value  = self.read(self.make_temp_variable(item_type))

        i       = self.read(self.make_temp_variable(reference))
        i_value = self.read(self.make_temp_variable(item_type))

        sizes_old = self.read(self._collection_sizes)
        sizes_new = self.read(self._collection_sizes.increment())
        sizes_i   = self.read(self.make_temp_variable(reference))

        self._expressions.extend([
            # for some reason this works better when items are symbolic
            has_item == z3.Exists(
                [c_value],
                z3.And(
                    c_value == item,
                    z3.Select(z3.Select(p_old, dst), c_value) == TRUE,
                )
            ),

            # actual operation
            z3.If(
                has_item,

                # item is already present - noop
                z3.And(
                    p_new == p_old,
                    sizes_new == sizes_old,
                ),

                # container modification is required
                z3.And(
                    # copying other instances
                    z3.ForAll(
                        [i],
                        z3.Implies(
                            i != dst,
                            z3.Select(p_new, i) == z3.Select(p_old, i)
                        ),
                    ),

                    # making the change
                    z3.ForAll(
                        [i_value],
                        z3.Implies(
                            i_value != item,
                            z3.Select(z3.Select(p_new, dst), i_value)
                            ==
                            z3.Select(z3.Select(p_old, dst), i_value)
                        )
                    ),
                    z3.Select(z3.Select(p_new, dst), item) == TRUE,

                    # updating the size counter
                    z3.ForAll(
                        [sizes_i],
                        z3.Implies(
                            sizes_i != dst,
                            z3.Select(sizes_new, sizes_i) == z3.Select(sizes_old, sizes_i)
                        ),
                    ),
                    z3.Select(sizes_new, dst) == z3.Select(sizes_old, dst) + 1,
                ),
            ),
        ])


    def set_ref_remove(self, dst: z3.ExprRef, item: z3.ExprRef, item_type: PrimitiveTypeInfo) -> None:
        pool  = self.get_set_pool_for(item_type)
        p_old = self.read(pool)
        p_new = self.read(pool.increment())

        has_item = self.read(self.make_temp_variable(boolean))
        c_value  = self.read(self.make_temp_variable(item_type))

        i       = self.read(self.make_temp_variable(reference))
        i_value = self.read(self.make_temp_variable(item_type))

        sizes_old = self.read(self._collection_sizes)
        sizes_new = self.read(self._collection_sizes.increment())
        sizes_i   = self.read(self.make_temp_variable(reference))

        self._expressions.extend([
            # for some reason this works better when items are symbolic
            has_item == z3.Exists(
                [c_value],
                z3.And(
                    c_value == item,
                    z3.Select(z3.Select(p_old, dst), c_value) == TRUE,
                )
            ),

            # actual operation
            z3.If(
                has_item,

                # removal is required
                z3.And(
                    # copying other instances
                    z3.ForAll(
                        [i],
                        z3.Implies(
                            i != dst,
                            z3.Select(p_new, i) == z3.Select(p_old, i)
                        ),
                    ),

                    # making the change
                    z3.ForAll(
                        [i_value],
                        z3.Implies(
                            i_value != item,
                            z3.Select(z3.Select(p_new, dst), i_value)
                            ==
                            z3.Select(z3.Select(p_old, dst), i_value)
                        )
                    ),
                    z3.Select(z3.Select(p_new, dst), item) == FALSE,

                    # updating the size counter
                    z3.ForAll(
                        [sizes_i],
                        z3.Implies(
                            sizes_i != dst,
                            z3.Select(sizes_new, sizes_i) == z3.Select(sizes_old, sizes_i)
                        ),
                    ),
                    z3.Select(sizes_new, dst) == z3.Select(sizes_old, dst) - 1,
                ),

                # item is not present - noop
                z3.And(
                    p_new == p_old,
                    sizes_new == sizes_old,
                )
            ),
        ])


    def set_ref_union(self, src_a: z3.ExprRef, src_b: z3.ExprRef, dst: z3.ExprRef, item_type: PrimitiveTypeInfo) -> None:
        pool  = self.get_set_pool_for(item_type)
        p_old = self.read(pool)
        p_new = self.read(pool.increment())

        i       = self.read(self.make_temp_variable(reference))
        i_value = self.read(self.make_temp_variable(item_type))

        sizes_old = self.read(self._collection_sizes)
        sizes_new = self.read(self._collection_sizes.increment())
        sizes_i   = self.read(self.make_temp_variable(reference))
        size_type = cast(ArrayTypeInfo, self._collection_sizes.variable.type).item_type
        size      = self.read(self.make_temp_variable(size_type))

        self._expressions.extend([
            # copy other instances
            z3.ForAll(
                [i],
                z3.Implies(
                    i != dst,
                    z3.Select(p_new, i) == z3.Select(p_old, i)
                ),
            ),

            # make changes
            z3.ForAll(
                [i_value],
                z3.Select(z3.Select(p_new, dst), i_value) == z3.Or(
                    z3.Select(z3.Select(p_old, src_a), i_value),
                    z3.Select(z3.Select(p_old, src_b), i_value)
                )
            ),

            # update size
            z3.ForAll(
                [sizes_i],
                z3.Implies(
                    sizes_i != dst,
                    z3.Select(sizes_new, sizes_i) == z3.Select(sizes_old, sizes_i)
                ),
            ),

            size >= self._wrap_primitive(0, size_type),  # this might help?
            size >= z3.If(
                z3.Select(sizes_old, src_a) >= z3.Select(sizes_old, src_b),
                z3.Select(sizes_old, src_a),
                z3.Select(sizes_old, src_b)
            ),
            size <= z3.Select(sizes_old, src_a) + z3.Select(sizes_old, src_b),

            z3.Select(sizes_new, dst) == size,
        ])


    def set_ref_intersection(self, src_a: z3.ExprRef, src_b: z3.ExprRef, dst: z3.ExprRef, item_type: PrimitiveTypeInfo) -> None:
        pool  = self.get_set_pool_for(item_type)
        p_old = self.read(pool)
        p_new = self.read(pool.increment())

        i       = self.read(self.make_temp_variable(reference))
        i_value = self.read(self.make_temp_variable(item_type))

        sizes_old = self.read(self._collection_sizes)
        sizes_new = self.read(self._collection_sizes.increment())
        sizes_i   = self.read(self.make_temp_variable(reference))
        size_type = cast(ArrayTypeInfo, self._collection_sizes.variable.type).item_type
        size      = self.read(self.make_temp_variable(size_type))

        self._expressions.extend([
            # copy other instances
            z3.ForAll(
                [i],
                z3.Implies(
                    i != dst,
                    z3.Select(p_new, i) == z3.Select(p_old, i)
                ),
            ),

            # make changes
            z3.ForAll(
                [i_value],
                z3.Select(z3.Select(p_new, dst), i_value) == z3.And(
                    z3.Select(z3.Select(p_old, src_a), i_value),
                    z3.Select(z3.Select(p_old, src_b), i_value)
                )
            ),

            # update size
            z3.ForAll(
                [sizes_i],
                z3.Implies(
                    sizes_i != dst,
                    z3.Select(sizes_new, sizes_i) == z3.Select(sizes_old, sizes_i)
                ),
            ),

            size >= self._wrap_primitive(0, size_type),
            size <= z3.If(
                z3.Select(sizes_old, src_a) <= z3.Select(sizes_old, src_b),
                z3.Select(sizes_old, src_a),
                z3.Select(sizes_old, src_b)
            ),

            z3.Select(sizes_new, dst) == size,
        ])


    def set_ref_equals(self, src_a: z3.ExprRef, src_b: z3.ExprRef, item_type: PrimitiveTypeInfo) -> z3.ExprRef:
        pool = self.get_set_pool_for(item_type)
        pool = self.read(pool)

        item   = self.read(self.make_temp_variable(item_type))
        output = self.read(self.make_temp_variable(boolean))

        self._expressions.append(
            output == z3.ForAll(
                [item],
                z3.Select(z3.Select(pool, src_a), item)
                ==
                z3.Select(z3.Select(pool, src_b), item)
            )
        )
        return output


    def map_ref_init(self, dst: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        pool  = self.read(self.get_map_pool_for(kv_type))
        key   = self.read(self.make_temp_variable(kv_type[0]))
        value = self.read(self.make_temp_variable(kv_type[1]))

        self._expressions.extend([
            # specify the size and type
            self.array_get(self._object_types, dst) == self._typeid_to_seq(typeid_name_for_map(*kv_type)),
            self.array_get(self._collection_sizes, dst) == 0,

            # make the initial assumption - there are no key-value pairs in this map
            z3.ForAll(
                [key, value],
                z3.Select(z3.Select(pool, dst), key, value) == FALSE
            ),
        ])
        self._register_new_map(self._last_ref, kv_type)


    def map_ref_has_key(self, src: z3.ExprRef, key: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> z3.ExprRef:
        pool    = self.read(self.get_map_pool_for(kv_type))
        c_key   = self.read(self.make_temp_variable(kv_type[0]))
        c_value = self.read(self.make_temp_variable(kv_type[1]))
        return z3.Exists(
            [c_key, c_value],
            z3.And(
                c_key == key,
                z3.Select(z3.Select(pool, src), c_key, c_value) == TRUE,
            )
        )


    def map_ref_has_value(self, src: z3.ExprRef, value: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> z3.ExprRef:
        pool    = self.read(self.get_map_pool_for(kv_type))
        c_key   = self.read(self.make_temp_variable(kv_type[0]))
        c_value = self.read(self.make_temp_variable(kv_type[1]))
        return z3.Exists(
            [c_key, c_value],
            z3.And(
                c_value == value,
                z3.Select(z3.Select(pool, src), c_key, c_value) == TRUE,
            )
        )


    def map_ref_has_pair(self, src: z3.ExprRef, key: z3.ExprRef, value: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> z3.ExprRef:
        pool = self.read(self.get_map_pool_for(kv_type))
        return z3.Select(z3.Select(pool, src), key, value) == TRUE


    def map_ref_get(self, src: z3.ExprRef, key: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> z3.ExprRef:
        pool  = self.read(self.get_map_pool_for(kv_type))
        value = self.read(self.make_temp_variable(kv_type[1]))
        self._expressions.append(
            z3.Select(z3.Select(pool, src), key, value) == TRUE
        )
        return value


    def map_ref_get_any_kv(self, src: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> tuple[z3.ExprRef, z3.ExprRef]:
        pool  = self.read(self.get_map_pool_for(kv_type))
        key   = self.read(self.make_temp_variable(kv_type[0]))
        value = self.read(self.make_temp_variable(kv_type[1]))
        self._expressions.append(
            z3.Select(z3.Select(pool, src), key, value) == TRUE
        )
        return (key, value)


    def map_ref_set(self, dst: z3.ExprRef, key: z3.ExprRef, value: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        pool  = self.get_map_pool_for(kv_type)
        p_old = self.read(pool)
        p_new = self.read(pool.increment())

        key_type, value_type = kv_type
        has_key    = self.read(self.make_temp_variable(boolean))
        c_value    = self.read(self.make_temp_variable(value_type))
        value_old  = self.read(self.make_temp_variable(value_type))
        same_value = self.read(self.make_temp_variable(boolean))

        i10       = self.read(self.make_temp_variable(reference))
        i10_key   = self.read(self.make_temp_variable(key_type))
        i10_value = self.read(self.make_temp_variable(value_type))
        i0        = self.read(self.make_temp_variable(reference))
        i0_key    = self.read(self.make_temp_variable(key_type))
        i0_value  = self.read(self.make_temp_variable(value_type))

        sizes_old = self.read(self._collection_sizes)
        sizes_new = self.read(self._collection_sizes.increment())
        sizes_i   = self.read(self.make_temp_variable(reference))

        self._expressions.extend([
            # temporary variables
            has_key == z3.Exists(
                [c_value],
                z3.And(
                    c_value == value_old,
                    z3.Select(z3.Select(p_old, dst), key, c_value) == TRUE,
                )
            ),
            same_value == (value == value_old),

            # actual operation
            z3.If(
                has_key,

                # key is present and there is a value associated with it
                z3.And(
                    # no change in size
                    sizes_new == sizes_old,

                    z3.If(
                        same_value,

                        # value is present and it's the same - noop
                        p_new == p_old,

                        # new value is different
                        z3.And(
                            # copy other instances
                            z3.ForAll(
                                [i10],
                                z3.Implies(
                                    i10 != dst,
                                    z3.Select(p_new, i10) == z3.Select(p_old, i10)
                                ),
                            ),

                            # making the change
                            z3.ForAll(
                                [i10_key, i10_value],
                                z3.Implies(
                                    z3.Or(
                                        i10_key != key,
                                        z3.And(
                                            i10_value != value,
                                            i10_value != value_old,
                                        )
                                    ),
                                    z3.Select(z3.Select(p_new, dst), i10_key, i10_value)
                                    ==
                                    z3.Select(z3.Select(p_old, dst), i10_key, i10_value)
                                )
                            ),
                            z3.Select(z3.Select(p_new, dst), key, value_old) == FALSE,
                            z3.Select(z3.Select(p_new, dst), key, value) == TRUE,
                        )
                    ),
                ),

                # the key is new
                z3.And(
                    # copy other instances
                    z3.ForAll(
                        [i0],
                        z3.Implies(
                            i0 != dst,
                            z3.Select(p_new, i0) == z3.Select(p_old, i0)
                        ),
                    ),

                    # making the change
                    z3.ForAll(
                        [i0_key, i0_value],
                        z3.Implies(
                            z3.Or(
                                i0_key   != key,
                                i0_value != value,
                            ),
                            z3.Select(z3.Select(p_new, dst), i0_key, i0_value)
                            ==
                            z3.Select(z3.Select(p_old, dst), i0_key, i0_value)
                        )
                    ),
                    z3.Select(z3.Select(p_new, dst), key, value) == TRUE,

                    # update the size counter
                    z3.ForAll(
                        [sizes_i],
                        z3.Implies(
                            sizes_i != dst,
                            z3.Select(sizes_new, sizes_i) == z3.Select(sizes_old, sizes_i)
                        ),
                    ),
                    z3.Select(sizes_new, dst) == z3.Select(sizes_old, dst) + 1,
                )
            )
        ])


    def map_ref_remove_key(self, dst: z3.ExprRef, key: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        pool  = self.get_map_pool_for(kv_type)
        p_old = self.read(pool)
        p_new = self.read(pool.increment())

        key_type, value_type = kv_type

        has_key = self.read(self.make_temp_variable(boolean))
        c_value = self.read(self.make_temp_variable(value_type))
        n_value = self.read(self.make_temp_variable(value_type))

        i       = self.read(self.make_temp_variable(reference))
        i_key   = self.read(self.make_temp_variable(key_type))
        i_value = self.read(self.make_temp_variable(value_type))

        sizes_old = self.read(self._collection_sizes)
        sizes_new = self.read(self._collection_sizes.increment())
        sizes_i   = self.read(self.make_temp_variable(reference))

        self._expressions.extend([
            # optimization
            has_key == z3.Exists(
                [c_value],
                z3.Select(z3.Select(p_old, dst), key, c_value) == TRUE,
            ),

            # actual operation
            z3.If(
                has_key,

                # need to switch this kv-pair to being 'not present'
                z3.And(
                    # copy other instances
                    z3.ForAll(
                        [i],
                        z3.Implies(
                            i != dst,
                            z3.Select(p_new, i) == z3.Select(p_old, i)
                        ),
                    ),

                    # making the change
                    z3.ForAll(
                        [i_key, i_value],
                        z3.Implies(
                            i_key != key,
                            z3.Select(z3.Select(p_new, dst), i_key, i_value)
                            ==
                            z3.Select(z3.Select(p_old, dst), i_key, i_value)
                        )
                    ),
                    z3.ForAll(
                        [n_value],
                        z3.Select(z3.Select(p_new, dst), key, n_value) == FALSE
                    ),

                    # updating the size counter
                    z3.ForAll(
                        [sizes_i],
                        z3.Implies(
                            sizes_i != dst,
                            z3.Select(sizes_new, sizes_i) == z3.Select(sizes_old, sizes_i)
                        ),
                    ),
                    z3.Select(sizes_new, dst) == z3.Select(sizes_old, dst) - 1,
                ),

                # nothing to change - the key is not present
                z3.And(
                    p_new == p_old,
                    sizes_new == sizes_old,
                )
            )
        ])


    def map_ref_union(self, src_a: z3.ExprRef, src_b: z3.ExprRef, dst: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        pool  = self.get_map_pool_for(kv_type)
        p_old = self.read(pool)
        p_new = self.read(pool.increment())

        i       = self.read(self.make_temp_variable(reference))
        i_key   = self.read(self.make_temp_variable(kv_type[0]))
        i_value = self.read(self.make_temp_variable(kv_type[1]))

        sizes_old = self.read(self._collection_sizes)
        sizes_new = self.read(self._collection_sizes.increment())
        sizes_i   = self.read(self.make_temp_variable(reference))
        size_type = cast(ArrayTypeInfo, self._collection_sizes.variable.type).item_type
        size      = self.read(self.make_temp_variable(size_type))

        self._expressions.extend([
            # copy other instances
            z3.ForAll(
                [i],
                z3.Implies(
                    i != dst,
                    z3.Select(p_new, i) == z3.Select(p_old, i)
                ),
            ),

            # make changes
            z3.ForAll(
                [i_key, i_value],
                z3.Select(z3.Select(p_new, dst), i_key, i_value) == z3.Or(
                    z3.Select(z3.Select(p_old, src_a), i_key, i_value),
                    z3.Select(z3.Select(p_old, src_b), i_key, i_value)
                )
            ),

            # update size
            z3.ForAll(
                [sizes_i],
                z3.Implies(
                    sizes_i != dst,
                    z3.Select(sizes_new, sizes_i) == z3.Select(sizes_old, sizes_i)
                ),
            ),
            z3.And(
                size >= 0,  # this might help?
                size >= z3.If(
                    z3.Select(sizes_old, src_a) >= z3.Select(sizes_old, src_b),
                    z3.Select(sizes_old, src_a),
                    z3.Select(sizes_old, src_b)
                ),
                size <= z3.Select(sizes_old, src_a) + z3.Select(sizes_old, src_b),
            ),
            z3.Select(sizes_new, dst) == size,
        ])


    def map_ref_intersection(self, src_a: VersionedVariable, src_b: VersionedVariable, dst: VersionedVariable, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        pool  = self.get_map_pool_for(kv_type)
        p_old = self.read(pool)
        p_new = self.read(pool.increment())

        i       = self.read(self.make_temp_variable(reference))
        i_key   = self.read(self.make_temp_variable(kv_type[0]))
        i_value = self.read(self.make_temp_variable(kv_type[1]))

        sizes_old = self.read(self._collection_sizes)
        sizes_new = self.read(self._collection_sizes.increment())
        sizes_i   = self.read(self.make_temp_variable(reference))
        size_type = cast(ArrayTypeInfo, self._collection_sizes.variable.type).item_type
        size      = self.read(self.make_temp_variable(size_type))

        self._expressions.extend([
            # copy other instances
            z3.ForAll(
                [i],
                z3.Implies(
                    i != dst,
                    z3.Select(p_new, i) == z3.Select(p_old, i)
                ),
            ),

            # make changes
            z3.ForAll(
                [i_key, i_value],
                z3.Select(z3.Select(p_new, dst), i_key, i_value) == z3.And(
                    z3.Select(z3.Select(p_old, src_a), i_key, i_value),
                    z3.Select(z3.Select(p_old, src_b), i_key, i_value)
                )
            ),

            # update size
            z3.ForAll(
                [sizes_i],
                z3.Implies(
                    sizes_i != dst,
                    z3.Select(sizes_new, sizes_i) == z3.Select(sizes_old, sizes_i)
                ),
            ),
            z3.And(
                size >= 0,
                size <= z3.If(
                    z3.Select(sizes_old, src_a) <= z3.Select(sizes_old, src_b),
                    z3.Select(sizes_old, src_a),
                    z3.Select(sizes_old, src_b)
                ),
            ),
            z3.Select(sizes_new, dst) == size,
        ])


    def map_ref_equals(self, src_a: z3.ExprRef, src_b: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> z3.ExprRef:
        pool = self.get_map_pool_for(kv_type)
        pool = self.read(pool)

        key    = self.read(self.make_temp_variable(kv_type[0]))
        value  = self.read(self.make_temp_variable(kv_type[1]))
        output = self.read(self.make_temp_variable(boolean))

        self._expressions.append(
            output == z3.ForAll(
                [key, value],
                z3.Select(z3.Select(pool, src_a), key, value)
                ==
                z3.Select(z3.Select(pool, src_b), key, value)
            )
        )
        return output


    def transform_ref_init(self, dst: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        pool = self.read(self.get_transform_pool_for(kv_type))
        key  = self.read(self.make_temp_variable(kv_type[0]))

        self._expressions.extend([
            # specify the size and type
            self.array_get(self._object_types, dst) == self._typeid_to_seq(typeid_name_for_transform(*kv_type)),
            self.array_get(self._collection_sizes, dst) == INVALID_SIZE,
        ])
        if kv_type[1] is boolean:
            self._expressions.extend([
                # make the initial assumption
                z3.ForAll(
                    [key],
                    z3.Select(z3.Select(pool, dst), key) == kv_type[1].default_value
                ),
            ])
        self._register_new_transform(self._last_ref, kv_type)


    def transform_ref_get(self, src: z3.ExprRef, key: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> z3.ExprRef:
        pool = self.read(self.get_transform_pool_for(kv_type))
        return z3.Select(z3.Select(pool, src), key)


    def transform_ref_set(self, dst: z3.ExprRef, key: z3.ExprRef, value: z3.ExprRef, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        pool  = self.get_transform_pool_for(kv_type)
        v_old = self.read(pool)
        v_new = self.read(pool.increment())

        v_old_tr = z3.Select(v_old, dst)
        v_new_tr = z3.Select(v_new, dst)

        v_iter_outer = self.read(self.make_temp_variable(reference))
        v_iter_inner = self.read(self.make_temp_variable(kv_type[0]))

        self._expressions.extend([
            # 'moving' over the old arrays array-by-array
            z3.ForAll(
                [v_iter_outer],
                z3.Implies(
                    v_iter_outer != dst,
                    z3.Select(v_new, v_iter_outer) == z3.Select(v_old, v_iter_outer)
                )
            ),

            # 'copying' old elements of the modified array
            z3.ForAll(
                [v_iter_inner],
                z3.Implies(
                    v_iter_inner != key,
                    z3.Select(v_new_tr, v_iter_inner) == z3.Select(v_old_tr, v_iter_inner)
                )
            ),

            # 'changing' the element
            z3.Select(v_new_tr, key) == value,
        ])


    def get_type_names_for_object(self, sinfo: StructureTypeInfo) -> list[str]:
        res = [sinfo.structure_name]
        res.extend(self._th_resolver.get_all_parents_of(sinfo.structure_name))
        res.sort()  # making exact checks stable
        return res


    def object_types_to_seq(self, types: list[str]) -> z3.SeqRef:
        return z3.simplify(
            z3.Concat(
                z3.Empty(self._typeid_seq_type.z3_sort),
                *[self._typeid_to_seq(typeid_name_for_structure(struct)) for struct in types],
            ),
        )


    def object_ref_init(self, ref: z3.ExprRef, structure_name: str) -> None:
        sinfo = self.context.structures[structure_name]
        self._expressions.extend([
            self.array_get(self._object_types, ref) == self.object_types_to_seq(self.get_type_names_for_object(sinfo)),
            self.array_get(self._collection_sizes, ref) == INVALID_SIZE,
        ])
        self._expressions.extend([
            self.object_field_read(ref, origin_class, field) == init
            for field, (init, origin_class) in self.get_object_fields_initializer_for(structure_name).items()
        ])
        self._register_new_structure(self._last_ref, sinfo)


    def object_is_instance_of(self, ref: z3.ExprRef, struct: str, exact: bool) -> z3.ExprRef:
        full_seq = self.array_get(self._object_types, ref)
        sinfo = self.context.structures[struct]

        if exact:
            types = self.get_type_names_for_object(sinfo)
            sub_seq = self.object_types_to_seq(types)
            return full_seq == sub_seq

        else:
            sub_seq = self.object_types_to_seq([sinfo.structure_name])
            validation = z3.Contains(full_seq, sub_seq)

            if not self.config.allow_type_unions and False:
                raise NotImplementedError()  # TODO: type unions

            return validation



    def object_field_read(self, ref: z3.ExprRef, struct: StructureTypeInfo, field: str) -> z3.ExprRef:
        pool = self.get_object_field_pool_for(struct, field)
        return self.array_get(pool, ref)


    def object_field_write(self, ref: z3.ExprRef, struct: StructureTypeInfo, field: str, value: z3.ExprRef) -> None:
        pool = self.get_object_field_pool_for(struct, field)
        self.array_set(pool, ref, value)


    def get_object_fields_initializer_for(self, structure_name: str) -> dict[str, tuple[z3.ExprRef, StructureTypeInfo]]:
        """
        field_name -> initializer + origin_class_info
        """
        return {
            fname: (init, self.context.structures[pclass])
            for fname, pclass in self._th_resolver.get_all_fields(structure_name).items()
            if (init := self.context.structures[pclass].fields[fname].type.default_value) is not None
        }


    def get_object_field_origin(self, struct: str, field: str) -> StructureTypeInfo:
        struct = self._th_resolver.get_field_origin(struct, field)
        return self.context.structures[struct]


    # === [instruction handling] ===========================================


    def visit_instruction_Noop(self, _: Noop) -> None:
        # nothing as expected
        pass


    def visit_instruction_PushPrimitive(self, inst: PushPrimitive) -> None:
        v = self._wrap_primitive(inst.value, inst.type)
        self.push(v)


    def visit_instruction_PushSymbolic(self, inst: PushSymbolic) -> None:
        self.push(self._make_symbolic(inst.type))


    def visit_instruction_Pop(self, _) -> None:
        _ = self.pull()


    def visit_instruction_SubroutineEnter(self, _: SubroutineEnter) -> None:
        self._stack_frame_number += 1


    def visit_instruction_SubroutineExit(self, _: SubroutineExit) -> None:
        self._stack_frame_number -= 1


    def visit_instruction_VariableRead(self, inst: VariableRead) -> None:
        src = self.to_versioned(inst.source_name, is_local=inst.source_is_local)
        if self.config.literal_substitution_enabled and (last_value := self._last_literal_value.get(src.variable.name)) is not None:
            src = last_value
        else:
            src = self.read(src)
        self.push(src)


    def visit_instruction_VariableWrite(self, inst: VariableWrite) -> None:
        value = self.simplify(self.pull())
        dst = self.to_versioned(inst.destination_name, is_local=inst.destination_is_local)
        self.write(dst, value)
        # caching for literal substitution during reading
        self._last_literal_value[dst.variable.name] = value if z3.z3util.is_expr_val(value) else None
        # TODO: apply the same idea to "fault flag" and "last exception"


    def visit_instruction_ContainerGetSize(self, _: ContainerGetSize) -> None:
        src = self.pull()
        res = self.array_get(self._collection_sizes, src)
        self.push(res)


    def visit_array_op_NEW(self, item_type: PrimitiveTypeInfo) -> None:
        size = self.pull()
        size = self.simplify(size)
        self._safeguard(
            size >= 0,
        )
        ref = self.new_reference()
        self.array_ref_init(ref, size, item_type)
        self.push(ref)


    def visit_array_op_SET_SIZE(self, item_type: PrimitiveTypeInfo) -> None:
        (dst, size) = self.pull(2)
        dst  = self.simplify(dst)
        size = self.simplify(size)
        self._safeguard(
            self.array_get(self._object_types, dst) == self._typeid_to_seq(typeid_name_for_array(item_type)),
        )
        self.array_set(self._collection_sizes, dst, size)


    def visit_array_op_GET(self, item_type: PrimitiveTypeInfo) -> None:
        (src, index) = self.pull(2)
        src   = self.simplify(src)
        index = self.simplify(index)
        self._safeguard(
            self.array_get(self._object_types, src) == self._typeid_to_seq(typeid_name_for_array(item_type)),
        )
        res = self.array_ref_get(src, index, item_type)
        self.push(res)


    def visit_array_op_SET(self, item_type: PrimitiveTypeInfo) -> None:
        (dst, index, value) = self.pull(3)
        dst   = self.simplify(dst)
        index = self.simplify(index)
        value = self.simplify(value)
        self._safeguard(
            self.array_get(self._object_types, dst) == self._typeid_to_seq(typeid_name_for_array(item_type)),
        )
        self.array_ref_set(dst, index, value, item_type)


    def visit_array_op_COPY(self, item_type: PrimitiveTypeInfo | None) -> None:
        (src, src_index, dst, dst_index, count) = self.pull(5)
        src       = self.simplify(src)
        src_index = self.simplify(src_index)
        dst       = self.simplify(dst)
        dst_index = self.simplify(dst_index)
        count     = self.simplify(count)

        if item_type is not None:
            type_id = self._typeid_to_seq(typeid_name_for_array(item_type))
            self._safeguard(
                self.array_get(self._object_types, src) == type_id,
                self.array_get(self._object_types, dst) == type_id,
            )

        self.array_ref_copy(src, src_index, dst, dst_index, count, item_type)


    def visit_array_op_EQUALS_RANGE(self, item_type: PrimitiveTypeInfo) -> None:
        (a, a_index, b, b_index, count) = self.pull(5)
        a       = self.simplify(a)
        a_index = self.simplify(a_index)
        b       = self.simplify(b)
        b_index = self.simplify(b_index)
        count   = self.simplify(count)

        type_id = self._typeid_to_seq(typeid_name_for_array(item_type))
        self._safeguard(
            self.array_get(self._object_types, a) == type_id,
            self.array_get(self._object_types, b) == type_id,
        )

        res = self.array_ref_equals_range(a, a_index, b, b_index, count, item_type)
        self.push(res)


    def visit_instruction_ArrayOperation(self, inst: ArrayOperation) -> None:
        op_handler: Callable[[PrimitiveTypeInfo], None] | None = getattr(self, f"visit_array_op_{inst.operation.name}", None)
        if op_handler is None:
            raise AssertionError(f"No handler for Array::'{inst.operation.name}'")
        op_handler(inst.item_type)


    def visit_primitive_op_ADD(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a + b

    def visit_primitive_op_SUB(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a - b

    def visit_primitive_op_MUL(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a * b

    def visit_primitive_op_DIV(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a / b

    def visit_primitive_op_MOD(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a % b

    def visit_primitive_op_AND(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a & b

    def visit_primitive_op_OR(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a | b

    def visit_primitive_op_XOR(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a ^ b

    def visit_primitive_op_SHR(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a >> b

    def visit_primitive_op_SHL(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a << b

    def visit_primitive_op_EQ(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a == b

    def visit_primitive_op_NEQ(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a != b

    def visit_primitive_op_LESS(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a < b

    def visit_primitive_op_LEQ(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a <= b

    def visit_primitive_op_GREATER(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a > b

    def visit_primitive_op_GEQ(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return a >= b

    def visit_primitive_op_NEGATE(self) -> z3.ExprRef:
        a = self.pull()
        return -a

    def visit_primitive_op_NOT(self) -> z3.ExprRef:
        a = self.pull()
        return ~a

    def visit_primitive_op_ABS(self) -> None:
        a = self.pull()
        return z3.Abs(a)

    def visit_primitive_op_MIN(self) -> None:
        a, b = self.pull(2)
        return z3.If(a <= b, a, b)

    def visit_primitive_op_MAX(self) -> None:
        a, b = self.pull(2)
        return z3.If(a >= b, a, b)

    # WARNING: this returns an integer!
    def visit_primitive_op_FLOOR(self) -> None:
        a = self.pull()
        return z3.ToInt(a) if hasattr(a, 'is_real') else a

    def visit_instruction_PrimitiveOp(self, inst: PrimitiveOp) -> None:
        op_handler: Callable[[], z3.ExprRef] | None = getattr(self, f"visit_primitive_op_{inst.operation.name}", None)
        if op_handler is None:
            raise AssertionError(f"No handler for '{inst.operation.name}'")
        res = op_handler()
        self.push(res)


    def visit_instruction_ControlPoint(self, inst: ControlPoint) -> None:
        match self._control_check(inst.control_id):
            case True:
                pass  # do nothing, already checked earlier

            case False:
                self.is_running = False  # nothing more, already checked earlier

            case None:
                self.check()
                self._control_update(inst.control_id, self.is_running)


    def visit_instruction_Assume(self, _: Assume) -> None:
        expr = self.pull()
        self._expressions.append(expr)


    def visit_instruction_NewInstance(self, inst: NewInstance) -> None:
        ref = self.new_reference()
        self.object_ref_init(ref, inst.structure_name)
        self.push(ref)


    def visit_instruction_FreeInstance(self, _: FreeInstance) -> None:
        ref = self.pull()
        ref = self.simplify(ref)
        self._safeguard(
            # validation against "double free" faults
            self.array_get(self._object_types, ref) != NULL_TYPEID_SEQ,
        )
        self.array_set(self._object_types, ref, NULL_TYPEID_SEQ)
        self.array_set(self._collection_sizes, ref, INVALID_SIZE)


    def visit_instruction_Copy(self, inst: Copy) -> None:
        expr = self._stack[-inst.stack_position - 1]
        for _ in range(inst.number_of_copies):
            self.push(expr)


    def visit_instruction_FieldRead(self, inst: FieldRead) -> None:
        ref = self.pull()
        ref = self.simplify(ref)
        origin_class = self.get_object_field_origin(inst.source_structure_name, inst.source_field_name)
        self._safeguard(
            self.array_get(self._object_types, ref) != NULL_TYPEID_SEQ,
        )
        res = self.object_field_read(ref, origin_class, inst.source_field_name)
        self.push(res)


    def visit_instruction_FieldWrite(self, inst: FieldWrite) -> None:
        (ref, value) = self.pull(2)
        ref   = self.simplify(ref)
        value = self.simplify(value)
        origin_class = self.get_object_field_origin(inst.destination_structure_name, inst.destination_field_name)
        self._safeguard(
            self.array_get(self._object_types, ref) != NULL_TYPEID_SEQ,
        )
        self.object_field_write(ref, origin_class, inst.destination_field_name, value)


    def visit_instruction_InstanceOf(self, inst: InstanceOf) -> None:
        ref = self.pull()
        res = self.object_is_instance_of(ref, inst.expected_structure_name, inst.exact_match)
        self.push(res)


    def visit_set_op_NEW(self, item_type: PrimitiveTypeInfo) -> None:
        ref = self.new_reference()
        self.set_ref_init(ref, item_type)
        self.push(ref)


    def visit_set_op_CONTAINS(self, item_type: PrimitiveTypeInfo) -> None:
        (ref, item) = self.pull(2)
        ref  = self.simplify(ref)
        item = self.simplify(item)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_set(item_type)),
        )
        res = self.set_ref_contains(ref, item, item_type)
        self.push(res)


    def visit_set_op_ANY_ITEM(self, item_type: PrimitiveTypeInfo) -> None:
        ref = self.pull()
        ref = self.simplify(ref)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_set(item_type)),
        )
        value = self.set_ref_get_any(ref, item_type)
        self.push(value)


    def visit_set_op_ADD(self, item_type: PrimitiveTypeInfo) -> None:
        (ref, value) = self.pull(3)
        ref   = self.simplify(ref)
        value = self.simplify(value)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_set(item_type)),
        )
        self.set_ref_add(ref, value, item_type)


    def visit_set_op_REMOVE(self, item_type: PrimitiveTypeInfo) -> None:
        (ref, item) = self.pull(2)
        ref  = self.simplify(ref)
        item = self.simplify(item)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_set(item_type)),
        )
        self.set_ref_remove(ref, item, item_type)


    def visit_set_op_UNION(self, item_type: PrimitiveTypeInfo) -> None:
        (src_a, src_b, dst) = self.pull(3)
        src_a = self.simplify(src_a)
        src_b = self.simplify(src_b)
        dst   = self.simplify(dst)

        type_id = self._typeid_to_seq(typeid_name_for_set(item_type))
        self._safeguard(
            self.array_get(self._object_types, src_a) == type_id,
            self.array_get(self._object_types, src_b) == type_id,
            self.array_get(self._object_types, dst)   == type_id,
        )

        self.set_ref_union(src_a, src_b, dst, item_type)


    def visit_set_op_INTERSECTION(self, item_type: PrimitiveTypeInfo) -> None:
        (src_a, src_b, dst) = self.pull(3)
        src_a = self.simplify(src_a)
        src_b = self.simplify(src_b)
        dst   = self.simplify(dst)

        type_id = self._typeid_to_seq(typeid_name_for_set(item_type))
        self._safeguard(
            self.array_get(self._object_types, src_a) == type_id,
            self.array_get(self._object_types, src_b) == type_id,
            self.array_get(self._object_types, dst)   == type_id,
        )

        self.set_ref_intersection(src_a, src_b, dst, item_type)


    def visit_set_op_EQUALS(self, item_type: PrimitiveTypeInfo) -> None:
        (src_a, src_b) = self.pull(2)
        src_a = self.simplify(src_a)
        src_b = self.simplify(src_b)

        type_id = self._typeid_to_seq(typeid_name_for_set(item_type))
        self._safeguard(
            self.array_get(self._object_types, src_a) == type_id,
            self.array_get(self._object_types, src_b) == type_id,
        )

        res = self.set_ref_equals(src_a, src_b, item_type)
        self.push(res)


    def visit_instruction_SetOperation(self, inst: SetOperation) -> None:
        op_handler: Callable[[PrimitiveTypeInfo], None] | None = getattr(self, f"visit_set_op_{inst.operation.name}", None)
        if op_handler is None:
            raise AssertionError(f"No handler for Set::'{inst.operation.name}'")
        op_handler(inst.item_type)


    def visit_map_op_NEW(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        ref = self.new_reference()
        self.map_ref_init(ref, kv_type)
        self.push(ref)


    def visit_map_op_GET(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        (ref, key) = self.pull(2)
        ref = self.simplify(ref)
        key = self.simplify(key)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_map(*kv_type)),
        )
        res = self.map_ref_get(ref, key, kv_type)
        self.push(res)


    def visit_map_op_SET(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        (ref, key, value) = self.pull(3)
        ref   = self.simplify(ref)
        key   = self.simplify(key)
        value = self.simplify(value)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_map(*kv_type)),
        )
        self.map_ref_set(ref, key, value, kv_type)


    def visit_map_op_REMOVE(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        (ref, key) = self.pull(2)
        ref = self.simplify(ref)
        key = self.simplify(key)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_map(*kv_type)),
        )
        self.map_ref_remove_key(ref, key, kv_type)


    def visit_map_op_HAS_KEY(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        (ref, key) = self.pull(2)
        ref = self.simplify(ref)
        key = self.simplify(key)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_map(*kv_type)),
        )
        res = self.map_ref_has_key(ref, key, kv_type)
        self.push(res)


    def visit_map_op_HAS_VALUE(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        (ref, value) = self.pull(2)
        ref   = self.simplify(ref)
        value = self.simplify(value)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_map(*kv_type)),
        )
        res = self.map_ref_has_value(ref, value, kv_type)
        self.push(res)


    def visit_map_op_HAS_PAIR(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        (ref, key, value) = self.pull(3)
        ref   = self.simplify(ref)
        key   = self.simplify(key)
        value = self.simplify(value)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_map(*kv_type)),
        )
        res = self.map_ref_has_pair(ref, key, value, kv_type)
        self.push(res)


    def visit_map_op_ANY_KEY(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        ref = self.pull()
        ref = self.simplify(ref)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_map(*kv_type)),
        )
        key, _ = self.map_ref_get_any_kv(ref, kv_type)
        self.push(key)


    def visit_map_op_ANY_VALUE(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        ref = self.pull()
        ref = self.simplify(ref)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_map(*kv_type)),
        )
        _, value = self.map_ref_get_any_kv(ref, kv_type)
        self.push(value)


    def visit_map_op_UNION(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        (src_a, src_b, dst) = self.pull(3)
        src_a = self.simplify(src_a)
        src_b = self.simplify(src_b)
        dst   = self.simplify(dst)

        type_id = self._typeid_to_seq(typeid_name_for_map(*kv_type))
        self._safeguard(
            self.array_get(self._object_types, src_a) == type_id,
            self.array_get(self._object_types, src_b) == type_id,
            self.array_get(self._object_types, dst)   == type_id,
        )

        self.map_ref_union(src_a, src_b, dst, kv_type)


    def visit_map_op_INTERSECTION(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        (src_a, src_b, dst) = self.pull(3)
        src_a = self.simplify(src_a)
        src_b = self.simplify(src_b)
        dst   = self.simplify(dst)

        type_id = self._typeid_to_seq(typeid_name_for_map(*kv_type))
        self._safeguard(
            self.array_get(self._object_types, src_a) == type_id,
            self.array_get(self._object_types, src_b) == type_id,
            self.array_get(self._object_types, dst)   == type_id,
        )

        self.map_ref_intersection(src_a, src_b, dst, kv_type)


    def visit_map_op_EQUALS(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        (src_a, src_b) = self.pull(2)
        src_a = self.simplify(src_a)
        src_b = self.simplify(src_b)

        type_id = self._typeid_to_seq(typeid_name_for_map(*kv_type))
        self._safeguard(
            self.array_get(self._object_types, src_a) == type_id,
            self.array_get(self._object_types, src_b) == type_id,
        )

        res = self.map_ref_equals(src_a, src_b, kv_type)
        self.push(res)


    def visit_instruction_MapOperation(self, inst: MapOperation) -> None:
        op_handler: Callable[[tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]], None] | None = getattr(self, f"visit_map_op_{inst.operation.name}", None)
        if op_handler is None:
            raise AssertionError(f"No handler for Map::'{inst.operation.name}'")
        op_handler(inst.kv_type)


    def visit_transform_op_NEW(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        ref = self.new_reference()
        self.transform_ref_init(ref, kv_type)
        self.push(ref)


    def visit_transform_op_GET(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        (ref, key) = self.pull(2)
        ref = self.simplify(ref)
        key = self.simplify(key)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_transform(*kv_type)),
        )
        res = self.transform_ref_get(ref, key, kv_type)
        self.push(res)


    def visit_transform_op_SET(self, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        (ref, key, value) = self.pull(3)
        ref   = self.simplify(ref)
        key   = self.simplify(key)
        value = self.simplify(value)
        self._safeguard(
            self.array_get(self._object_types, ref) == self._typeid_to_seq(typeid_name_for_transform(*kv_type)),
        )
        self.transform_ref_set(ref, key, value, kv_type)


    def visit_instruction_TransformOperation(self, inst: TransformOperation) -> None:
        op_handler: Callable[[tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]], None] | None = getattr(self, f"visit_transform_op_{inst.operation.name}", None)
        if op_handler is None:
            raise AssertionError(f"No handler for Transform::'{inst.operation.name}'")
        op_handler(inst.kv_type)


    def visit_instruction_SimpleDiff(self, inst: SimpleDiff) -> None:
        is_same = self.pull()
        res = z3.If(
            is_same,
            self._wrap_primitive(0, inst.result_type),
            self._wrap_primitive(1, inst.result_type),
        )
        self.push(res)


    def visit_instruction_DistinctValues(self, inst: DistinctValues) -> None:
        values = self.pull(inst.value_count)
        if not isinstance(values, (list, tuple)):
            values = [values]
        res = z3.Distinct(*values)
        self.push(res)


    def visit_instruction_FaultStatusRead(self, _: FaultStatusRead) -> None:
        status = self.read(self._fault_flag)
        self.push(status)


    def visit_instruction_FaultStatusClear(self, _: FaultStatusClear) -> None:
        self.write(self._fault_flag, FALSE)


    def visit_instruction_ExceptionRead(self, _: ExceptionRead) -> None:
        ref = self.read(self._last_exception)
        self.push(ref)


    def visit_instruction_ExceptionWrite(self, _: ExceptionWrite) -> None:
        ref = self.pull(1)
        self.write(self._last_exception, ref)


    def visit_instruction_ClearStackToBoundary(self, inst: ClearStackToBoundary) -> None:
        if inst.boundary is None:
            self._stack.clear()
        else:
            while len(self._stack) > 0 and inst.boundary != self._stack[-1]:
                self._stack.pop()


    def visit_instruction_PushStackBoundary(self, inst: PushStackBoundary) -> None:
        self._stack.append(inst.boundary)


    def visit_string_op_LENGTH(self) -> z3.ExprRef:
        s = self.pull()
        return z3.Length(s)

    def visit_string_op_CONCAT(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return z3.Concat(a, b)

    def visit_string_op_CONTAINS(self) -> z3.ExprRef:
        a, b = self.pull(2)
        return z3.Contains(a, b)

    def visit_string_op_INDEX_OF(self) -> z3.ExprRef:
        s, substr, offset = self.pull(3)
        offset = self._ensure_integer(offset)
        return z3.IndexOf(s, substr, offset)

    def visit_string_op_LAST_INDEX_OF(self) -> z3.ExprRef:
        s, substr = self.pull(2)
        return z3.LastIndexOf(s, substr)

    def visit_string_op_STARTS_WITH(self) -> z3.ExprRef:
        s, prefix = self.pull(2)
        return z3.PrefixOf(prefix, s)

    def visit_string_op_ENDS_WITH(self) -> z3.ExprRef:
        s, suffix = self.pull(2)
        return z3.SuffixOf(suffix, s)

    def visit_string_op_COPY(self) -> z3.ExprRef:
        s, offset, count = self.pull(3)
        offset = self._ensure_integer(offset)
        count  = self._ensure_integer(count)
        return z3.SubString(s, offset, count)

    def visit_string_op_REPLACE_ONCE(self) -> z3.ExprRef:
        s, old, new = self.pull(3)
        return z3.Replace(s, old, new)

    def visit_string_op_INT_TO_STR(self) -> z3.ExprRef:
        value = self.pull()
        value = self._ensure_integer(value)
        return z3.IntToStr(value)

    def visit_string_op_STR_TO_INT(self) -> z3.ExprRef:
        value = self.pull()
        return z3.StrToInt(value)

    def visit_string_op_ORD(self) -> z3.ExprRef:
        value = self.pull()
        return z3.StrToCode(value)

    def visit_instruction_StringOperation(self, inst: StringOperation) -> None:
        op_handler: Callable[[], None] | None = getattr(self, f"visit_string_op_{inst.operation.name}", None)
        if op_handler is None:
            raise AssertionError(f"No handler for String::'{inst.operation.name}'")
        res = op_handler()
        self.push(res)


    def visit_instruction_ContainerTypeCheck(self, inst: ContainerTypeCheck) -> None:
        src = self.pull()
        type_id = None
        match inst.container_kind:
            case ContainerKind.ARRAY:
                type_id = typeid_name_for_array(*inst.item_types)
            case ContainerKind.SET:
                type_id = typeid_name_for_set(*inst.item_types)
            case ContainerKind.MAP:
                type_id = typeid_name_for_map(*inst.item_types)
            case ContainerKind.TRANSFORM:
                type_id = typeid_name_for_transform(*inst.item_types)
            case _:
                raise AssertionError(f"Unsupported container kind: {inst.container_kind.name}")
        self.push(
            self.array_get(self._object_types, src) == self._typeid_to_seq(type_id)
        )


    def _register_new_array(self, reference: int, item_type: PrimitiveTypeInfo) -> None:
        self.statistics.arrays[reference] = item_type


    def _register_new_set(self, reference: int, item_type: PrimitiveTypeInfo) -> None:
        self.statistics.sets[reference] = item_type


    def _register_new_map(self, reference: int, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        self.statistics.maps[reference] = kv_type


    def _register_new_transform(self, reference: int, kv_type: tuple[PrimitiveTypeInfo, PrimitiveTypeInfo]) -> None:
        self.statistics.transforms[reference] = kv_type


    def _register_new_structure(self, reference: int, type: StructureTypeInfo) -> None:
        self.statistics.structures[reference] = type


    # === [public interface] ===============================================


    def step(self, instruction: Instruction) -> bool:
        if not self._is_initialized:
            self._init_symbols()

        if self.is_running:
            self._instruction_resolver.visit(instruction)

        return self.is_running


    def play(self, instructions: Iterable[Instruction]) -> None:
        for inst in instructions:
            if not self.step(inst):
                return


    def execute(self, instructions: Iterable[Instruction], *, flush: bool = False) -> bool:
        self.is_running = True
        self.play(instructions)

        if flush:
            self.flush_execution_stack()

        if self.is_running:
            # sanity checks
            if (leftover_count := len(self._stack)) != 0:
                print(f"[!] There are {leftover_count} unused item(s) left on top of the execution stack!")
            if self._stack_frame_number != 0:
                print(f"[!] Invalid last stack frame index: {self._stack_frame_number}")

            # performing extra check here to be sure, control instruction may not be always present at the end
            self.check()
        return self.is_running


    def show_expressions(self) -> None:
        print('------------------------------------------', flush=False)
        z3.set_pp_option('bounded', False)
        z3.set_pp_option('max_width', 1000)
        for expr in self._expressions:
            print(expr, flush=False)
        print('------------------------------------------', flush=True)


    def show_stack(self) -> None:
        print('------------------------------------------', flush=False)
        z3.set_pp_option('bounded', False)
        z3.set_pp_option('max_width', 1000)
        for i, item in enumerate(self._stack):
            print(f"#{i:3} :", repr(item), flush=False)
        print('------------------------------------------', flush=True)


    def flush_execution_stack(self) -> None:
        self._stack.clear()
        self._stack_frame_number = 0


