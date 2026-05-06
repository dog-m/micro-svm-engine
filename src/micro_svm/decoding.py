from dataclasses import dataclass
from enum import Enum, auto
from typing import final

import z3

from .descriptors import VariableInfo
from .execution import (
    SymbolicStateMachine,
    VersionedVariable,
    typeid_name_for_array,
    typeid_name_for_map,
    typeid_name_for_set,
    typeid_name_for_structure,
    typeid_name_for_transform,
)
from .global_context import GlobalContext
from .instructions import *  # noqa: F403
from .type_hierarchy import TypeHierarchyResolver
from .types import *  # noqa: F403


@final
class ModelDecoder:
    def __init__(self, ctx: GlobalContext, th_resolver: TypeHierarchyResolver, machine: SymbolicStateMachine):
        assert ctx is not None
        assert th_resolver is not None
        assert machine is not None
        self.ctx = ctx
        self.th_resolver = th_resolver
        self.machine = machine
        #
        self._container_types: dict[str, TypeInfo] | None = None


    def decode_value(self, source: z3.ExprRef, type: TypeInfo) -> ValueType:
        value = self.machine._last_model.eval(source, model_completion=True)

        if type.is_primitive():
            value = value.py_value()
            if value is None:
                raise AssertionError("Value is None")
            return value
        else:
            raise AssertionError(f"Unexpected non-primitive type: {type}")


    def _check_container_size(self, container: list, expected_size: int) -> None:
        actual_size = len(container)
        if actual_size != expected_size:
            amount = 'LESS' if actual_size < expected_size else 'MORE'
            print(f"[!] Decoded {amount} items than expected! ({actual_size} != {expected_size})")


    def _decode_array(self, version: int | None, ref: z3.ExprRef | int, type: ArrayTypeInfo, size: int) -> list[ValueType]:
        pool = self.machine.get_array_ref_pools_for(type.item_type)[0]
        container = z3.Select(self.machine._variable_cache.resolve(pool, version), ref)
        container = self.machine._last_model.eval(container, model_completion=True)

        result: list[ValueType] = []
        # this is less efficient but more reliable
        for i in range(size):
            value = self.decode_value(z3.Select(container, i), type.item_type)
            result.append(value)

        return result


    def _decode_set(self, version: int | None, ref: z3.ExprRef | int, type: SetTypeInfo, size: int) -> list[ValueType]:
        pool = self.machine.get_set_pool_for(type.item_type)
        container = z3.Select(self.machine._variable_cache.resolve(pool, version), ref)
        container = self.machine._last_model.eval(container, model_completion=True)

        result = []
        while z3.is_store(container):
            item  = self.decode_value(container.arg(1), type.item_type)
            store = self.decode_value(container.arg(2), boolean)
            if store:
                result.append(item)
            container = container.arg(0)

        self._check_container_size(result, size)

        result.sort()  # keeping things stable
        return result


    def _decode_map(self, version: int | None, ref: z3.ExprRef | int, type: MapTypeInfo, size: int) -> list[tuple[ValueType, ValueType]]:
        pool = self.machine.get_map_pool_for(type.kv_type)
        container = z3.Select(self.machine._variable_cache.resolve(pool, version), ref)
        container = self.machine._last_model.eval(container, model_completion=True)

        result: list[tuple[ValueType, ValueType]] = []
        while z3.is_store(container):
            key     = self.decode_value(container.arg(1), type.key_type)
            value   = self.decode_value(container.arg(2), type.value_type)
            present = self.decode_value(container.arg(3), boolean)
            if present:
                result.append((key, value))
            container = container.arg(0)

        self._check_container_size(result, size)

        result.sort(key=lambda pair: pair[0])  # keeping things stable
        return result


    def _decode_transform(self, version: int | None, ref: z3.ExprRef | int, type: TransformTypeInfo) -> list[tuple[ValueType, ValueType]]:
        pool = self.machine.get_transform_pool_for(type.kv_type)
        container = z3.Select(self.machine._variable_cache.resolve(pool, version), ref)
        container = self.machine._last_model.eval(container, model_completion=True)

        result: list[tuple[ValueType, ValueType]] = []
        while z3.is_store(container):
            key   = self.decode_value(container.arg(1), type.key_type)
            value = self.decode_value(container.arg(2), type.value_type)
            result.append((key, value))
            container = container.arg(0)
        # WARNING: in some cases a single pair might be missing! (solver has decided to put it as "default"/"else" value)

        result.sort(key=lambda pair: pair[0])  # keeping things stable
        return result


    def _decode_structure(self, version: int | None, ref: z3.ExprRef | int, type: StructureTypeInfo) -> dict[str, tuple[ValueType, PrimitiveTypeInfo]]:
        m_context  = self.machine.context
        m_resolver = self.machine._th_resolver
        m_cache    = self.machine._variable_cache

        fields: set[str] = set()
        fields.update(type.fields.keys())
        for parent in m_resolver.get_all_parents_of(type.structure_name):
            pinfo = m_context.structures[parent]
            fields.update(pinfo.fields.keys())

        result: dict[str, tuple[ValueType, PrimitiveTypeInfo]] = {}
        for field_name in sorted(fields):  # keeping things stable
            struct_origin = m_resolver.get_field_origin(type.structure_name, field_name)
            struct_origin = m_context.structures[struct_origin]

            ftype = struct_origin.fields[field_name].type

            pool = self.machine.get_object_field_pool_for(struct_origin, field_name)
            fvalue = z3.Select(m_cache.resolve(pool, version), ref)
            fvalue = self.decode_value(fvalue, ftype)

            result[field_name] = (fvalue, ftype)

        return result


    def decode_reference(self, ref: z3.ExprRef | int, type: TypeInfo, version: int | None):
        # null-reference
        if isinstance(ref, int):
            if ref == 0:
                return None
        elif self.machine._last_model.eval(ref, model_completion=True).py_value() == 0:
            return None

        if type.is_reference():
            assert isinstance(type, TypedReferenceTypeInfo)
            type = type.target_type

        size = z3.Select(self.machine._variable_cache.resolve(self.machine._collection_sizes, version), ref)
        size = max(0, self.machine._last_model.eval(size, model_completion=True).py_value())

        if isinstance(type, ArrayTypeInfo):
            return self._decode_array(version, ref, type, size)
        elif isinstance(type, SetTypeInfo):
            return self._decode_set(version, ref, type, size)
        elif isinstance(type, MapTypeInfo):
            return self._decode_map(version, ref, type, size)
        elif isinstance(type, TransformTypeInfo):
            return self._decode_transform(version, ref, type)
        elif isinstance(type, StructureTypeInfo):
            return self._decode_structure(version, ref, type)
        else:
            raise ValueError(f"Unsupported reference type: {type}")


    def decode(self, vv: VersionedVariable, *, version: int | None = None, resolve_reference: bool = False):
        if self.machine._last_model is None:
            return None

        type = vv.variable.type
        if not type.is_primitive():
            raise ValueError(f"Unable to decode {vv.variable}: (not a primitive)")

        src = self.machine._variable_cache.resolve(vv, version)
        if resolve_reference and type.is_reference():
            if isinstance(type, UntypedReferenceTypeInfo):
                type = self.infer_reference_type(src)
            assert isinstance(type, TypedReferenceTypeInfo), f"Unable to resolve opaque reference: {vv.variable}"
            return self.decode_reference(src, type, version)

        else:
            return self.decode_value(src, type)


    def _get_basic_container_types(self) -> dict[str, TypeInfo]:
        container_types = self._container_types
        if container_types is None:
            container_types = self._container_types = {}
            for id_gen, type_gen in [(typeid_name_for_array, array), (typeid_name_for_set, set_of)]:
                for item_type in PRIMITIVE_TYPES:
                    id = id_gen(item_type)
                    container_types[id] = type_gen(item_type)

            for id_gen, type_gen in [(typeid_name_for_map, map_of), (typeid_name_for_transform, transform_of)]:
                for key_type in PRIMITIVE_TYPES:
                    for value_type in PRIMITIVE_TYPES:
                        id = id_gen(key_type, value_type)
                        container_types[id] = type_gen(key_type, value_type)

        return container_types


    def infer_reference_type(self, object_ref: z3.ExprRef | int) -> TypedReferenceTypeInfo | None:
        if isinstance(object_ref, int):
            type = self.machine.statistics.resolve_ref_type(object_ref)
            if type is not None:
                return type

        type_id: z3.SeqRef = z3.Select(self.machine.read(self.machine._object_types), object_ref)
        type_id: z3.SeqRef = self.machine._last_model.eval(type_id, model_completion=True)
        type_id: set[str]  = self.machine.typeid_sequence_to_names(type_id)

        # check basic container types
        for container_type_id, type in self._get_basic_container_types().items():
            if container_type_id in type_id:
                return ref(type)

        candidate: TypeInfo | None = None
        candidate_parent_count: int = -1
        for sinfo in self.ctx.structures.values():
            if typeid_name_for_structure(sinfo.structure_name) in type_id:
                pcount = len(self.th_resolver.get_all_parents_of(sinfo.structure_name))
                if pcount > candidate_parent_count:
                    candidate = sinfo
                    candidate_parent_count = pcount
        if candidate is None:
            print('[!] No suitable struct candidates were found!')

        return ref(candidate) if candidate is not None else None



@final
class ValueOrigin(Enum):
    VARIABLE  = auto()
    FIELD     = auto()
    ARRAY     = auto()
    SET       = auto()
    MAP       = auto()
    TRANSFORM = auto()


size_t = integer


@dataclass
class Source:
    origin: ValueOrigin
    retrieval_args: list[object]

    def __repr__(self):
        return f"({self.origin.name}, {self.retrieval_args})"

    def to_instructions(self, ref_handles: dict[int, VariableRead]) -> list[Instruction]:
        args = self.retrieval_args
        match self.origin:
            case ValueOrigin.VARIABLE:
                name, locality = args
                return [VariableRead(name, locality == 'local')]

            case ValueOrigin.FIELD:
                object_ref, structure_name, field_name = args
                return [
                    ref_handles[object_ref],
                    FieldRead(structure_name, field_name),
                ]

            case ValueOrigin.ARRAY:
                container_ref, i = args
                return [
                    ref_handles[container_ref],
                    PushPrimitive(i, size_t),
                    ArrayOperation(ArrayOps.GET, reference),
                ]

            case ValueOrigin.SET:
                container_ref = args[0]
                return [
                    ref_handles[container_ref],
                    PushPrimitive(i, size_t),
                    SetOperation(SetOps.ANY_ITEM, reference),
                ]

            case ValueOrigin.MAP:
                container_ref, k_or_v = args[0]
                return [
                    ref_handles[container_ref],
                    PushPrimitive(i, size_t),
                    MapOperation(MapOps.ANY_KEY if k_or_v == 'key' else MapOps.ANY_VALUE, reference),
                ]

            case ValueOrigin.TRANSFORM:
                name, locality = args
                return [VariableRead(name, locality == 'local')]

            case _:
                raise AssertionError(f"Unexpected origin: {self.origin}")



@dataclass
class ReferenceInfo:
    type: TypeInfo
    sources: list[Source]

    def get_grounding(self) -> Source | None:
        for s in self.sources:
            if s.origin is ValueOrigin.VARIABLE:
                return s
        return None



@final
class StateIntermediateDescription:
    def __init__(self):
        self.reachability_map: dict[int, ReferenceInfo] = {}
        self.structure_instances: set[int] = set()
        self.collection_sizes: dict[int, int] = {}  # ref -> size
        self.structure_count = 0
        self.collection_count = 0
        #
        self._values: dict[str | int, InitializerValueType] = {}


    def get_value(self, identifier: str) -> InitializerValueType:
        return self._values[identifier]


    def is_container(self, ref: int) -> bool:
        return ref in self.collection_sizes


    @staticmethod
    def analyze(
        m: SymbolicStateMachine,
        local_variables: list[VariableInfo],
        th_resolver: TypeHierarchyResolver,
        context: GlobalContext,
    ) -> 'StateIntermediateDescription':
        state = StateIntermediateDescription()
        decoder = ModelDecoder(context, th_resolver, m)

        queue: list[tuple[int, Source]] = []
        def schedule(ref: int, source: ValueOrigin, args: list[object]) -> None:
            if ref != 0:
                queue.append((ref, Source(source, args)))

        for variable in local_variables:
            vv = m.to_versioned(variable.name, is_local=True, stack_frame=0)
            value = state._values[variable.name] = decoder.decode_value(m.read(vv), reference)
            if variable.type.is_reference():
                schedule(value, ValueOrigin.VARIABLE, [variable.name, 'local'])

        for variable in context.global_variables.values():
            vv = m.to_versioned(variable.name)
            value = state._values[variable.name] = decoder.decode_value(m.read(vv), reference)
            if variable.type.is_reference():
                schedule(value, ValueOrigin.VARIABLE, [variable.name, 'global'])

        # building dependency network
        while queue:
            ref, source = queue.pop()
            if ref in state.reachability_map:
                state.reachability_map[ref].sources.append(source)

            else:
                type = decoder.infer_reference_type(ref).target_type
                value = state._values[ref] = decoder.decode_reference(ref, type, version=0)
                state.reachability_map[ref] = ReferenceInfo(type, [source])
                unique_refs: set[int] = set()

                if isinstance(type, StructureTypeInfo):
                    state.structure_instances.add(ref)
                    state.structure_count += 1
                    for fname, (fvalue, ftype) in value.items():
                        if ftype.is_reference() and fvalue not in unique_refs:
                            unique_refs.add(fvalue)
                            schedule(fvalue, ValueOrigin.FIELD, [ref, type.structure_name, fname])

                elif isinstance(type, (ArrayTypeInfo, SetTypeInfo)):
                    state.collection_sizes[ref] = len(value)
                    state.collection_count += 1
                    if type.item_type.is_reference():
                        if isinstance(type, ArrayTypeInfo):
                            for i, item in enumerate(value):
                                if item not in unique_refs:
                                    unique_refs.add(item)
                                    schedule(item, ValueOrigin.ARRAY, [ref, i])
                        else:
                            # all items are expected to be unique in a set
                            for item in value:
                                schedule(item, ValueOrigin.SET, [ref])

                elif isinstance(type, (MapTypeInfo, TransformTypeInfo)):
                    state.collection_sizes[ref] = len(value)
                    state.collection_count += 1  # 'transform' is 'container-like' but anyway
                    rkey   = type.key_type.is_reference()
                    rvalue = type.value_type.is_reference()
                    if rkey or rvalue:
                        source = ValueOrigin.MAP if isinstance(type, MapTypeInfo) else ValueOrigin.TRANSFORM
                        for (k, v) in value:
                            if rkey and k not in unique_refs:
                                unique_refs.add(k)
                                schedule(k, source, [ref])

                            if rvalue and v not in unique_refs:
                                unique_refs.add(v)
                                schedule(v, source, [ref])

                else:
                    raise AssertionError(f"Unexpected type: {type}")

        return state

