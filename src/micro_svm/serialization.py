import json
from typing import Callable, final

from .cfg import *  # noqa: F403
from .descriptors import CompiledSubroutine, FunctionInfo, VariableInfo
from .global_context import GlobalContext
from .instructions import *  # noqa: F403
from .state import ObjectState, ProgramState, VariableState
from .types import *  # noqa: F403


def _order_string_list(items: list[str] | None) -> list[str] | None:
    # keeping things git-friendly
    return None if items is None else sorted(items)



@final
class TypeEncoder:
    def __init__(self):
        pass

    def _encode_fields(self, fields: list[FieldInfo]) -> list[object]:
        return {
            f.name: {
                'type': self.encode_type_reference(f.type),
                'tags': _order_string_list(f.tags),
            }
            for f in fields
        }

    def encode_structure(self, struct: StructureTypeInfo) -> dict[str, object]:
        return {
            '_': 'structure',
            'name': struct.structure_name,
            'parents': _order_string_list(struct.parents),
            'fields': self._encode_fields(struct.fields.values()),
        }

    def encode_type_reference(self, type: TypeInfo | None) -> dict[str, object] | None:
        if type is None:
            return None
        else:
            if isinstance(type, KnownReferenceTypeInfo):
                return {
                    '_': 'ref',
                    'item': self.encode_type_reference(type.target_type),
                }
            elif isinstance(type, OpaqueReferenceTypeInfo):
                return {
                    '_': 'ref',
                }
            elif isinstance(type, ArrayTypeInfo):
                return {
                    '_': type.name,
                    'item': self.encode_type_reference(type.item_type),
                }
            elif isinstance(type, SetTypeInfo):
                return {
                    '_': type.name,
                    'item': self.encode_type_reference(type.item_type),
                }
            elif isinstance(type, MapTypeInfo):
                return {
                    '_': type.name,
                    'key': self.encode_type_reference(type.key_type),
                    'value': self.encode_type_reference(type.value_type),
                }
            elif isinstance(type, TransformTypeInfo):
                return {
                    '_': type.name,
                    'key': self.encode_type_reference(type.key_type),
                    'value': self.encode_type_reference(type.value_type),
                }
            elif isinstance(type, StructureTypeInfo):
                return {
                    '_': 'structure',
                    'name': type.structure_name,
                }
            elif isinstance(type, PrimitiveTypeInfo):
                return {
                    '_': type.name,
                }
            else:
                raise AssertionError(f"Unsupported type reference: {type}")



@final
class GlobalVariableEncoder:
    def __init__(self, type_encoder: TypeEncoder):
        assert type_encoder is not None
        self.type_encoder = type_encoder

    def encode_variable(self, variable: VariableInfo) -> dict[str, object]:
        return {
            'type': self.type_encoder.encode_type_reference(variable.type),
            'initializer': variable.initializer,
            'tags': _order_string_list(variable.tags),
        }



@final
class NodeEnumerator:
    def __init__(self):
        self.counter = 0
        self.id_mapping: dict[int, str] = {}

    def get_name_for(self, node: Node | None) -> str | None:
        if node is None:
            return None
        else:
            key = id(node)
            if key in self.id_mapping:
                return self.id_mapping[key]
            else:
                v = f"#{self.counter:04x}"  # 0000..ffff ("65536 nodes" is plenty for a "pretty experiment")
                self.id_mapping[key] = v
                self.counter += 1
                return v



@final
class FunctionEncoder:
    def __init__(self, type_encoder: TypeEncoder, enumerator: NodeEnumerator):
        assert type_encoder is not None and enumerator is not None
        self.type_encoder = type_encoder
        self.enumerator = enumerator

    def _encode_parameter(self, pname: str, ptype: TypeInfo) -> dict[str, object]:
        return {
            'name': pname,
            'type': self.type_encoder.encode_type_reference(ptype),
        }

    def _encode_local_variable(self, variable: VariableInfo) -> dict[str, object]:
        return {
            'name': variable.name,
            'type': self.type_encoder.encode_type_reference(variable.type),
            'tags': _order_string_list(variable.tags),
        }

    def _encode_implementation(self, func: FunctionInfo) -> dict[str, object] | None:
        impl = func.implementation
        if impl is None:
            return None
        else:
            return {
                'entry': self.enumerator.get_name_for(impl.entry_node),
                'local-variables': [
                    self._encode_local_variable(v) for v in impl.local_variables
                ],
            }

    def encode_function_header(self, func: FunctionInfo) -> dict[str, object]:
        return {
            'original-name': func.original_name,
            'structure': func.structure,
            'parameters': [
                self._encode_parameter(pname, ptype) for pname, ptype in func.parameters.items()
            ],
            'result-type': self.type_encoder.encode_type_reference(func.result_type),
            'static': func.is_static,
            'tags': _order_string_list(func.tags),
            'implementation': self._encode_implementation(func),
        }



@final
class InstructionEncoder:
    EMPTY = {}

    def __init__(self, type_encoder: TypeEncoder):
        assert type_encoder is not None
        self.type_encoder = type_encoder
        self.encoders: dict[object, Callable[[Instruction], dict[str, object]]] = {
            Noop:                 self._encode_Noop,
            ControlPoint:         self._encode_ControlPoint,
            PushPrimitive:        self._encode_PushPrimitive,
            PushSymbolic:         self._encode_PushSymbolic,
            Pop:                  self._encode_default,
            SubroutineEnter:      self._encode_default,
            SubroutineExit:       self._encode_default,
            VariableRead:         self._encode_VariableRead,
            VariableWrite:        self._encode_VariableWrite,
            PrimitiveOp:          self._encode_PrimitiveOp,
            Assume:               self._encode_default,
            ContainerGetSize:     self._encode_default,
            ArrayOperation:       self._encode_ArrayOperation,
            SetOperation:         self._encode_SetOperation,
            MapOperation:         self._encode_MapOperation,
            TransformOperation:   self._encode_TransformOperation,
            NewInstance:          self._encode_NewInstance,
            FreeInstance:         self._encode_default,
            Copy:                 self._encode_Copy,
            FieldRead:            self._encode_FieldRead,
            FieldWrite:           self._encode_FieldWrite,
            InstanceOf:           self._encode_InstanceOf,
            SimpleDiff:           self._encode_SimpleDiff,
            DistinctValues:       self._encode_DistinctValues,
            FaultStatusRead:      self._encode_default,
            FaultStatusClear:     self._encode_default,
            ExceptionRead:        self._encode_default,
            ExceptionWrite:       self._encode_default,
            ClearStackToBoundary: self._encode_ClearStackToBoundary,
            PushStackBoundary:    self._encode_PushStackBoundary,
            StringOperation:      self._encode_StringOperation,
            ContainerTypeCheck:   self._encode_ContainerTypeCheck,
        }

    def _encode_default(self, _: Instruction):
        return self.EMPTY

    def _encode_ArrayOperation(self, inst: ArrayOperation):
        return {
            'operation': inst.operation.name,
            'item-type': self.type_encoder.encode_type_reference(inst.item_type),
        }

    def _encode_SetOperation(self, inst: SetOperation):
        return {
            'operation': inst.operation.name,
            'item-type': self.type_encoder.encode_type_reference(inst.item_type),
        }

    def _encode_MapOperation(self, inst: MapOperation):
        key, value = inst.kv_type
        return {
            'operation': inst.operation.name,
            'key-type': self.type_encoder.encode_type_reference(key),
            'value-type': self.type_encoder.encode_type_reference(value),
        }

    def _encode_TransformOperation(self, inst: TransformOperation):
        key, value = inst.kv_type
        return {
            'operation': inst.operation.name,
            'key-type': self.type_encoder.encode_type_reference(key),
            'value-type': self.type_encoder.encode_type_reference(value),
        }

    def _encode_Noop(self, inst: Noop):
        return {
            'comment': inst.comment,
        }

    def _encode_ControlPoint(self, inst: ControlPoint):
        return {
            'control-id': inst.control_id,
        }

    def _encode_PushPrimitive(self, inst: PushPrimitive):
        return {
            'value': inst.value,
            'type': self.type_encoder.encode_type_reference(inst.type),
        }

    def _encode_PushSymbolic(self, inst: PushSymbolic):
        return {
            'type': self.type_encoder.encode_type_reference(inst.type),
        }

    def _encode_VariableRead(self, inst: VariableRead):
        return {
            'source-name': inst.source_name,
            'source-is-local': inst.source_is_local,
        }

    def _encode_VariableWrite(self, inst: VariableWrite):
        return {
            'destination-name': inst.destination_name,
            'destination-is-local': inst.destination_is_local,
        }

    def _encode_PrimitiveOp(self, inst: PrimitiveOp):
        return {
            'operation': inst.operation.name,
        }

    def _encode_NewInstance(self, inst: NewInstance):
        return {
            'structure-name': inst.structure_name,
        }

    def _encode_Copy(self, inst: Copy):
        return {
            'number-of-copies': inst.number_of_copies,
            'stack-position': inst.stack_position,
        }

    def _encode_FieldRead(self, inst: FieldRead):
        return {
            'source-structure-name': inst.source_structure_name,
            'source-field-name': inst.source_field_name,
        }

    def _encode_FieldWrite(self, inst: FieldWrite):
        return {
            'destination-structure-name': inst.destination_structure_name,
            'destination-field-name': inst.destination_field_name,
        }

    def _encode_InstanceOf(self, inst: InstanceOf):
        return {
            'expected-structure-name': inst.expected_structure_name,
            'exact-match': inst.exact_match,
        }

    def _encode_SimpleDiff(self, inst: SimpleDiff):
        return {
            'result-type': self.type_encoder.encode_type_reference(inst.result_type),
        }

    def _encode_DistinctValues(self, inst: DistinctValues):
        return {
            'value-count': inst.value_count,
        }

    def _encode_ClearStackToBoundary(self, inst: ClearStackToBoundary):
        return {
            'boundary': inst.boundary,
        }

    def _encode_PushStackBoundary(self, inst: PushStackBoundary):
        return {
            'boundary': inst.boundary,
        }

    def _encode_StringOperation(self, inst: StringOperation):
        return {
            'operation': inst.operation.name,
        }

    def _encode_ContainerTypeCheck(self, inst: ContainerTypeCheck):
        return {
            'container_kind': inst.container_kind.name,
            'values': [
                self.type_encoder.encode_type_reference(t)
                for t in inst.item_types
            ]
        }

    def encode_instruction(self, inst: Instruction) -> dict[str, object]:
        return {
            '_': inst.__class__.__name__,
            **self.encoders[inst.__class__](inst),
        }



# WARNING: this uses recursive approach when traversing sub-graphs!
@final
class CfgEncoder:
    def __init__(
            self,
            instruction_encoder: InstructionEncoder,
            enumerator: NodeEnumerator,
        ):
        assert instruction_encoder is not None and enumerator is not None
        assert enumerator is not None
        self._instruction_encoder = instruction_encoder
        self._enumerator = enumerator
        self._resolver = CFGNodeResolver(self)

    def visit_CFG_BasicBlock(self, node: BasicBlock) -> dict[str, object]:
        return {
            'instructions': [
                self._instruction_encoder.encode_instruction(inst) for inst in node.instructions
            ],
        }

    def visit_CFG_FailurePath(self, node: FailurePath) -> dict[str, object]:
        return {
            'metadata': node.metadata,
        }

    def visit_CFG_EndOfProgram(self, _: EndOfProgram) -> dict[str, object]:
        return {
            # as expected!
        }

    def visit_CFG_CallStatic(self, node: CallStatic) -> dict[str, object]:
        return {
            'function-name': node.function_name,
            'argument-count': node.argument_count,
        }

    def visit_CFG_CallVirtual(self, node: CallVirtual) -> dict[str, object]:
        return {
            'structure-name': node.structure_name,
            'method-name': node.method_name,
            'argument-count': node.argument_count,
        }

    def visit_CFG_MarkerFunctionExit(self, _: MarkerFunctionExit) -> dict[str, object]:
        return {
            # as expected!
        }

    def visit_CFG_While(self, node: While) -> dict[str, object]:
        return {
            'loop-id': node.loop_id,
            'condition': self._encode_node(node.condition),
            'body': self._encode_node(node.body),
        }

    def visit_CFG_MarkerLoopEnd(self, node: MarkerLoopEnd) -> dict[str, object]:
        return {
            'loop-id': node.loop_id,
        }

    def visit_CFG_MarkerLoopIterationEnd(self, node: MarkerLoopIterationEnd) -> dict[str, object]:
        return {
            'loop-id': node.loop_id,
        }

    def visit_CFG_Break(self, node: Break) -> dict[str, object]:
        return {
            'loop-id': node.loop_id,
        }

    def visit_CFG_Continue(self, node: Continue) -> dict[str, object]:
        return {
            'loop-id': node.loop_id,
        }

    def visit_CFG_TryBlock(self, node: TryBlock) -> dict[str, object]:
        return {
            'body': self._encode_node(node.body),
            'catch-handlers': [
                {
                    'structure-name': struct_name,
                    'handler': self._encode_node(handler)
                }
                for struct_name, handler in node.catch_handlers
            ],
            'finishing-section': self._encode_node(node.finishing_section),
        }

    def visit_CFG_MarkerTryBlockEnd(self, _: MarkerTryBlockEnd) -> dict[str, object]:
        return {
            # as expected!
        }

    def visit_CFG_Throw(self, _: Throw) -> dict[str, object]:
        return {
            # as expected!
        }

    def visit_CFG_Switch(self, node: Switch) -> dict[str, object]:
        return {
            'value_source': self._encode_node(node.value_source),
            'cumulative': node.cumulative,
            'cases': {
                self._encode_node(condition) : self._encode_node(handler)
                for (condition, handler) in node.cases
            },
        }

    def _encode_node(self, node: Node | None) -> str | None:
        if node is None:
            return None
        else:
            result = self._enumerator.get_name_for(node)  # trying to keep the sequence somewhat readable
            cfg_nodes = self.cfg_nodes
            assert cfg_nodes is not None
            while node is not None:
                id = self._enumerator.get_name_for(node)  # call order matters here
                cfg_nodes[id] = {
                    '_': node.__class__.__name__,
                    **self._resolver.visit(node),
                    'next': self._enumerator.get_name_for(node.next),
                }
                node = node.next
            return result

    def encode_function_body(self, func: FunctionInfo, cfg_nodes: dict[str, object]) -> None:
        if func.implementation is not None:
            self.cfg_nodes = cfg_nodes
            self._encode_node(func.implementation.entry_node)
            self.cfg_nodes = None


def _save_context_impl(spec: GlobalContext) -> object:
    te = TypeEncoder()
    gve = GlobalVariableEncoder(te)
    ne = NodeEnumerator()
    fe = FunctionEncoder(te, ne)
    ie = InstructionEncoder(te)
    ce = CfgEncoder(ie, ne)

    result: dict[str, object] = {}

    # NOTE: order might play a role in some rare(?) cases, thus it's a list
    r_types = result['types'] = []
    for struct in spec.structures.values():
        r_types.append(te.encode_structure(struct))

    r_globals = result['global-variables'] = {}
    for gv in spec.global_variables.values():
        r_globals[gv.name] = gve.encode_variable(gv)

    r_funcs = result['functions'] = {}
    r_nodes = result['cfg-nodes'] = {}
    for func in spec.functions.values():
        r_funcs[func.full_name] = fe.encode_function_header(func)
        ce.encode_function_body(func, r_nodes)

    return result



def save_context_to_string(ctx: GlobalContext, *, compact: bool = False) -> str:
    return json.dumps(
        _save_context_impl(ctx),
        ensure_ascii=False,
        indent=None if compact else 4,
        separators=(',', ':' if compact else ': '),
        #sort_keys=True,  # keeping things git-friendly
    )

def save_context_to_file(ctx: GlobalContext, file: object, *, compact: bool = False) -> None:
    json.dump(
        _save_context_impl(ctx),
        fp=file,
        ensure_ascii=False,
        indent=None if compact else 4,
        separators=(',', ':' if compact else ': '),
        #sort_keys=True,  # keeping things git-friendly
    )




@final
class TypeDecoder:
    def __init__(self, spec: GlobalContext):
        assert spec is not None
        self.spec = spec

    def decode_structure_head(self, info: dict[str, object]) -> None:
        self.spec.register_structure(
            name=info['name'],
            parents=info['parents'],
            fields=[
                # ignoring fields during this pass
            ]
        )

    def decode_structure_body(self, info: dict[str, object]) -> None:
        sinfo = self.spec.structures[info['name']]
        for fname, finfo in info['fields'].items():
            new_field = field(
                name=fname,
                type=self.decode_type_reference(finfo['type']),
                tags=set(finfo['tags']),
            )
            sinfo.fields[new_field.name] = new_field

    def decode_type_reference(self, info: dict[str, object] | None) -> TypeInfo | None:
        if info is None:
            return None
        else:
            match info['_']:
                case 'ref':
                    if 'item' in info:
                        return ref(self.decode_type_reference(info['item']))
                    else:
                        return reference
                case 'structure':
                    return self.spec.structures[info['name']]
                case 'array':
                    return array(self.decode_type_reference(info['item']))
                case 'set':
                    return set_of(self.decode_type_reference(info['item']))
                case 'map':
                    return map_of(
                        self.decode_type_reference(info['key']),
                        self.decode_type_reference(info['value'])
                    )
                case 'transform':
                    return transform_of(
                        self.decode_type_reference(info['key']),
                        self.decode_type_reference(info['value'])
                    )
                case 'boolean':
                    return boolean
                case 'int8':
                    return int8
                case 'int16':
                    return int16
                case 'int32':
                    return int32
                case 'int64':
                    return int64
                case 'integer':
                    return integer
                case 'real':
                    return real
                case 'char':
                    return char
                case 'string':
                    return string
                case o:
                    raise AssertionError(f"Unknown type reference: {repr(o)}")



@final
class GlobalVariableDecoder:
    def __init__(self, spec: GlobalContext, type_decoder: TypeDecoder):
        assert spec is not None
        assert type_decoder is not None
        self.spec = spec
        self.type_decoder = type_decoder

    def decode_variable(self, name: str, info: dict[str, object]) -> None:
        self.spec.register_global_variable(
            name=name,
            type=self.type_decoder.decode_type_reference(info['type']),
            initializer=info['initializer'],
            tags=set(info['tags']),
        )



@final
class FunctionDecoder:
    def __init__(self, spec: GlobalContext, type_decoder: TypeDecoder):
        assert spec is not None
        assert type_decoder is not None
        self.spec = spec
        self.type_decoder = type_decoder

    def _decode_implementation(self, info: dict[str, object], entry: Node | None) -> CompiledSubroutine | None:
        if entry is None:
            return None
        else:
            local_variables: list[VariableInfo] = []
            for vinfo in info['implementation']['local-variables']:
                variable = VariableInfo(
                    name=vinfo['name'],
                    type=self.type_decoder.decode_type_reference(vinfo['type']),
                    initializer=None,
                    tags=set(vinfo['tags']),
                )
                local_variables.append(variable)
            return CompiledSubroutine(entry, local_variables)

    def decode_function(
            self,
            full_name: str,
            info: dict[str, object],
            entry_node: Node | None) -> None:
        structure = info['structure']
        is_static = info['static']
        func = FunctionInfo(
            info['original-name'],
            structure=structure,
            parameters={
                pinfo['name']: self.type_decoder.decode_type_reference(pinfo['type'])
                for pinfo in info['parameters']
            },
            result_type=self.type_decoder.decode_type_reference(info['result-type']),
            is_static=is_static,
            tags=set(info['tags']),
        )
        func.implementation = self._decode_implementation(info, entry_node)
        if structure is not None:
            if is_static:
                self.spec.structures[structure].static_methods[func.original_name] = full_name
            else:
                self.spec.structures[structure].methods[func.original_name] = full_name
        self.spec.functions[full_name] = func
        self.spec.register_function_symbols(func)



@final
class InstructionDecoder:
    def __init__(self, type_decoder: TypeDecoder):
        assert type_decoder is not None
        self.type_decoder = type_decoder
        self.decoders: dict[str, Callable[[dict[str, object]], Instruction]] = {}
        self._set_decoder(Noop,                 self._decode_Noop)
        self._set_decoder(ControlPoint,         self._decode_ControlPoint)
        self._set_decoder(PushPrimitive,        self._decode_PushPrimitive)
        self._set_decoder(PushSymbolic,         self._decode_PushSymbolic)
        self._set_decoder(Pop,                  self._decode_default)
        self._set_decoder(SubroutineEnter,      self._decode_default)
        self._set_decoder(SubroutineExit,       self._decode_default)
        self._set_decoder(VariableRead,         self._decode_VariableRead)
        self._set_decoder(VariableWrite,        self._decode_VariableWrite)
        self._set_decoder(PrimitiveOp,          self._decode_PrimitiveOp)
        self._set_decoder(Assume,               self._decode_default)
        self._set_decoder(ContainerGetSize,     self._decode_default)
        self._set_decoder(ArrayOperation,       self._decode_ArrayOperation)
        self._set_decoder(SetOperation,         self._decode_SetOperation)
        self._set_decoder(MapOperation,         self._decode_MapOperation)
        self._set_decoder(TransformOperation,   self._decode_TransformOperation)
        self._set_decoder(NewInstance,          self._decode_NewInstance)
        self._set_decoder(FreeInstance,         self._decode_default)
        self._set_decoder(Copy,                 self._decode_Copy)
        self._set_decoder(FieldRead,            self._decode_FieldRead)
        self._set_decoder(FieldWrite,           self._decode_FieldWrite)
        self._set_decoder(InstanceOf,           self._decode_InstanceOf)
        self._set_decoder(SimpleDiff,           self._decode_SimpleDiff)
        self._set_decoder(DistinctValues,       self._decode_DistinctValues)
        self._set_decoder(FaultStatusRead,      self._decode_default)
        self._set_decoder(FaultStatusClear,     self._decode_default)
        self._set_decoder(ExceptionRead,        self._decode_default)
        self._set_decoder(ExceptionWrite,       self._decode_default)
        self._set_decoder(ClearStackToBoundary, self._decode_ClearStackToBoundary)
        self._set_decoder(PushStackBoundary,    self._decode_PushStackBoundary)
        self._set_decoder(StringOperation,      self._decode_StringOperation)
        self._set_decoder(ContainerTypeCheck,   self._decode_ContainerTypeCheck)

    def _set_decoder(self, clazz: type, decoder: Callable[[dict, type], Instruction]) -> None:
        self.decoders[clazz.__name__] = lambda info, c=clazz: decoder(info, c)

    def _decode_default(self, _: dict[str, object], ctor: type[Instruction]):
        return ctor()

    def _decode_ArrayOperation(self, info: dict[str, object], ctor: type[ArrayOperation]):
        return ctor(
            ArrayOps[info['operation']],
            self.type_decoder.decode_type_reference(info['item-type']),
        )

    def _decode_SetOperation(self, info: dict[str, object], ctor: type[SetOperation]):
        return ctor(
            SetOps[info['operation']],
            self.type_decoder.decode_type_reference(info['item-type']),
        )

    def _decode_MapOperation(self, info: dict[str, object], ctor: type[MapOperation]):
        return ctor(
            MapOps[info['operation']],
            (
                self.type_decoder.decode_type_reference(info['key-type']),
                self.type_decoder.decode_type_reference(info['value-type']),
            )
        )

    def _decode_TransformOperation(self, info: dict[str, object], ctor: type[TransformOperation]):
        return ctor(
            TransformOps[info['operation']],
            (
                self.type_decoder.decode_type_reference(info['key-type']),
                self.type_decoder.decode_type_reference(info['value-type']),
            )
        )

    def _decode_Noop(self, info: dict[str, object], ctor: type[Noop]):
        return ctor(
            info['comment'],
        )

    def _decode_ControlPoint(self, info: dict[str, object], ctor: type[ControlPoint]):
        return ctor(
            info['control-id'],
        )

    def _decode_PushPrimitive(self, info: dict[str, object], ctor: type[PushPrimitive]):
        return ctor(
            info['value'],
            self.type_decoder.decode_type_reference(info['type']),
        )

    def _decode_PushSymbolic(self, info: dict[str, object], ctor: type[PushSymbolic]):
        return ctor(
            self.type_decoder.decode_type_reference(info['type']),
        )

    def _decode_VariableRead(self, info: dict[str, object], ctor: type[VariableRead]):
        return ctor(
            info['source-name'],
            info['source-is-local'],
        )

    def _decode_VariableWrite(self, info: dict[str, object], ctor: type[VariableWrite]):
        return ctor(
            info['destination-name'],
            info['destination-is-local'],
        )

    def _decode_PrimitiveOp(self, info: dict[str, object], ctor: type[PrimitiveOp]):
        return ctor(
            PrimitiveOps[info['operation'].upper()],
        )

    def _decode_NewInstance(self, info: dict[str, object], ctor: type[NewInstance]):
        return ctor(
            info['structure-name'],
        )

    def _decode_Copy(self, info: dict[str, object], ctor: type[Copy]):
        return ctor(
            count=info['number-of-copies'],
            index=info['stack-position'],
        )

    def _decode_FieldRead(self, info: dict[str, object], ctor: type[FieldRead]):
        return ctor(
            info['source-structure-name'],
            info['source-field-name'],
        )

    def _decode_FieldWrite(self, info: dict[str, object], ctor: type[FieldWrite]):
        return ctor(
            info['destination-structure-name'],
            info['destination-field-name'],
        )

    def _decode_InstanceOf(self, info: dict[str, object], ctor: type[InstanceOf]):
        return ctor(
            info['expected-structure-name'],
            exact=info['exact-match'],
        )

    def _decode_SimpleDiff(self, info: dict[str, object], ctor: type[SimpleDiff]):
        return ctor(
            self.type_decoder.decode_type_reference(info['result-type']),
        )

    def _decode_DistinctValues(self, info: dict[str, object], ctor: type[DistinctValues]):
        return ctor(
            info['value-count'],
        )

    def _decode_ClearStackToBoundary(self, info: dict[str, object], ctor: type[ClearStackToBoundary]):
        return ctor(
            info['boundary'],
        )

    def _decode_PushStackBoundary(self, info: dict[str, object], ctor: type[PushStackBoundary]):
        return ctor(
            info['boundary'],
        )

    def _decode_StringOperation(self, info: dict[str, object], ctor: type[StringOperation]):
        return ctor(
            StringOps[info['operation'].upper()],
        )

    def _decode_ContainerTypeCheck(self, info: dict[str, object], ctor: type[ContainerTypeCheck]):
        return ctor(
            ContainerKind[info['container_kind']],
            [
                self.type_decoder.decode_type_reference(t)
                for t in info['item_types']
            ]
        )

    def decode_instruction(self, info: dict[str, object]) -> Instruction:
        decoder = self.decoders.get(info['_'])
        if decoder is None:
            raise AssertionError(f"No decoder for instruction: {info['_']}")
        else:
            return decoder(info)



# WARNING: this uses recursive approach for sub-graphs reconstruction!
# WARNING: this should be synchronized with encoding
@final
class CfgDecoder:
    def __init__(self, instruction_decoder: InstructionDecoder):
        assert instruction_decoder is not None
        self._instruction_decoder = instruction_decoder

    def _decode_BasicBlock(self, info: dict[str, object]) -> Node:
        node = BasicBlock()
        for inst in info['instructions']:
            instruction = self._instruction_decoder.decode_instruction(inst)
            node.instructions.append(instruction)
        return node

    def _decode_FailurePath(self, info: dict[str, object]) -> Node:
        return FailurePath(info['metadata'])

    def _decode_EndOfProgram(self, _: dict[str, object]) -> Node:
        return EndOfProgram()

    def _decode_CallStatic(self, info: dict[str, object]) -> Node:
        return CallStatic(
            signature=info['function-name'],
            argc=info['argument-count'],
        )

    def _decode_CallVirtual(self, info: dict[str, object]) -> Node:
        return CallVirtual(
            structure=info['structure-name'],
            method=info['method-name'],
            argc=info['argument-count'],
        )

    def _decode_MarkerFunctionExit(self, _: dict[str, object]) -> Node:
        return MarkerFunctionExit(
            # as expected!
        )

    def _decode_While(self, info: dict[str, object]) -> Node:
        info_condition = self.cfg_nodes[info['condition']]
        info_body      = self.cfg_nodes[info['body']]
        return While(
            loop_id=info['loop-id'],
            cond=self._decode_node(info_condition),
            body=self._decode_node(info_body),
        )

    def _decode_MarkerLoopEnd(self, info: dict[str, object]) -> Node:
        return MarkerLoopEnd(
            loop_id=info['loop-id'],
        )

    def _decode_MarkerLoopIterationEnd(self, info: dict[str, object]) -> Node:
        return MarkerLoopIterationEnd(
            loop_id=info['loop-id'],
        )

    def _decode_Break(self, info: dict[str, object]) -> Node:
        return Break(
            loop_id=info['loop-id'],
        )

    def _decode_Continue(self, info: dict[str, object]) -> Node:
        return Continue(
            loop_id=info['loop-id'],
        )

    def _decode_TryBlock(self, info: dict[str, object]) -> Node:
        body = self.cfg_nodes[info['body']]
        finishing_section = self.cfg_nodes[info['finishing-section']]

        node = TryBlock(self._decode_node(body))
        for handler_info in info['catch-handlers']:
            struct_name = handler_info['structure-name']
            handler = self.cfg_nodes[handler_info['handler']]
            impl = self._decode_node(handler)
            node.catch_handlers[struct_name] = impl
        node.finishing_section = self._decode_node(finishing_section)
        return node

    def _decode_MarkerTryBlockEnd(self, _: dict[str, object]) -> Node:
        return MarkerTryBlockEnd(
            # as expected!
        )

    def _decode_Throw(self, _: dict[str, object]) -> Node:
        return Throw(
            # as expected!
        )

    def _decode_Switch(self, info: dict[str, object]) -> Node:
        src = self.cfg_nodes.get(info['value_source'])
        node = Switch(self._decode_node(src))
        node.cumulative = info['cumulative']
        for condition, handler in info['cases'].items():
            node.cases.append((
                self._decode_node(self.cfg_nodes[condition]),
                self._decode_node(self.cfg_nodes[handler])
            ))
        return node

    def _decode_node(self, info: dict[str, object] | None) -> Node | None:
        result: Node | None = None
        last_node: Node = None
        while info is not None:
            decoder = getattr(self, f"_decode_{info['_']}", Node)
            if decoder is None:
                raise AssertionError(f"No decoder for {info['_']}")
            else:
                node: Node = decoder(info)
                if result is None:
                    result = node
                else:
                    last_node.next = node
                last_node = node
            next_id = info['next']
            info = None if next_id is None else self.cfg_nodes[next_id]
        return result

    def decode_function_body(
            self,
            function_info: dict[str, object],
            cfg_nodes: dict[str, object],
            ) -> Node | None:
        if function_info['implementation'] is None:
            return None
        else:
            entry_id = function_info['implementation']['entry']
            self.cfg_nodes = cfg_nodes
            entry = self._decode_node(cfg_nodes[entry_id])
            self.cfg_nodes = None
            return entry




def _load_context_impl(obj: dict[str, object]) -> GlobalContext:
    spec = GlobalContext()

    td = TypeDecoder(spec)
    gvd = GlobalVariableDecoder(spec, td)
    fd = FunctionDecoder(spec, td)
    id = InstructionDecoder(td)
    cd = CfgDecoder(id)

    for struct in obj['types']:
        td.decode_structure_head(struct)
    for struct in obj['types']:
        td.decode_structure_body(struct)

    for gname, ginfo in obj['global-variables'].items():
        gvd.decode_variable(gname, ginfo)

    o_funcs = obj['functions']
    o_nodes = obj['cfg-nodes']
    for full_name, finfo in o_funcs.items():
        entry = cd.decode_function_body(finfo, o_nodes)
        fd.decode_function(full_name, finfo, entry)

    return spec


def load_context_from_string(raw_data: str) -> GlobalContext:
    obj = json.loads(raw_data)
    return _load_context_impl(obj)

def load_context_from_file(file: object) -> GlobalContext:
    obj = json.load(file)
    return _load_context_impl(obj)




@final
class ProgramStateDecoder:
    def __init__(self, type_decoder: TypeDecoder):
        assert type_decoder is not None
        self.type_decoder = type_decoder

    def _validate_state_for_type(self, state: object, type: TypeInfo) -> InitializerValueType:
        is_valid = False
        if isinstance(type, (OpaqueReferenceTypeInfo, KnownReferenceTypeInfo)):
            # a name of an instance from the object pool or other variable name or 'null'
            is_valid = isinstance(state, str) or state is None
        elif isinstance(type, StructureTypeInfo):
            is_valid = isinstance(state, dict)
        elif isinstance(type, (ArrayTypeInfo, SetTypeInfo)):
            is_valid = isinstance(state, list)
        elif isinstance(type, (MapTypeInfo, TransformTypeInfo)):
            # i.e. pairs of values
            is_valid = isinstance(state, list) and all([len(item) == 2 and isinstance(item, (list, tuple)) for item in state])
        else:
            is_valid = state is None or isinstance(state, (str, int, float))
        if not is_valid:
            raise ValueError(f"Invalid value for type '{type}': {repr(state)}")
        return state

    def decode_object(self, name: str, info: dict[str, object]) -> ObjectState:
        type = self.type_decoder.decode_type_reference(info['type'])
        return ObjectState(
            id=name,
            type=type,
            state=self._validate_state_for_type(info['state'], type),
        )

    def decode_global_variable(self, name: str, value: InitializerValueType, info: VariableInfo) -> VariableState:
        return VariableState(
            name=name,
            state=self._validate_state_for_type(value, info.type),
        )



def _prune_unreachable_objects(state: ProgramState, ctx: GlobalContext) -> None:
    reachable: set[str] = set()

    queue: list[str] = []
    queue.extend(state.expected_objects.keys())
    for variable in state.global_variables.values():
        type = ctx.global_variables[variable.name].type
        if type.is_reference() and isinstance(variable.state, str):
            queue.append(variable.state)

    while len(queue) != 0:
        name = queue.pop()
        if name not in reachable and name in state.objects:
            reachable.add(name)
            o = state.objects[name]
            type = o.type
            if isinstance(type, (ArrayTypeInfo, SetTypeInfo)):
                if type.item_type.is_reference():
                    for item in o.state:
                        if isinstance(item, str):
                            queue.append(item)
            elif isinstance(type, (MapTypeInfo, TransformTypeInfo)):
                k_ref = type.key_type.is_reference()
                v_ref = type.value_type.is_reference()
                if k_ref or v_ref:
                    for (key, value) in o.state:  # list or pairs
                        if k_ref and isinstance(key, str):
                            queue.append(key)
                        if v_ref and isinstance(value, str):
                            queue.append(value)
            else:
                assert isinstance(o.state, dict)
                # being cautious here without analyzing the type hierarchy
                queue.extend(o.state.values())

    for name in list(state.objects.keys()):
        if name not in reachable:
            del state.objects[name]



def _load_state_impl(spec: GlobalContext, obj: dict[str, object], prune: bool) -> ProgramState:
    res = ProgramState()
    type_decoder = TypeDecoder(spec)
    state_decoder = ProgramStateDecoder(type_decoder)
    res.allow_object_reuse = obj.get('allow-object-reuse', True)

    for name, value in obj['global-variables'].items():
        info = spec.global_variables[name]
        res.global_variables[name] = state_decoder.decode_global_variable(name, value, info)

    o_objects = obj['all-objects']
    for name, info in o_objects.items():
        res.objects[name] = state_decoder.decode_object(name, info)

    for name in obj['expected-objects']:
        res.expected_objects[name] = res.objects[name]

    if prune:
        _prune_unreachable_objects(res, spec)

    return res


def load_state_from_file(ctx: GlobalContext, f: object, *, prune: bool = True):
    obj = json.load(f)
    return _load_state_impl(ctx, obj, prune)

def load_state_from_string(ctx: GlobalContext, raw_data: str, *, prune: bool = True):
    obj = json.loads(raw_data)
    return _load_state_impl(ctx, obj, prune)




@final
class ProgramStateEncoder:
    def __init__(self, type_encoder: TypeEncoder):
        assert type_encoder is not None
        self.type_encoder = type_encoder

    def encode_variable(self, vs: VariableState) -> object:
        return vs.state

    def encode_object(self, obj: ObjectState) -> object:
        return {
            'type': self.type_encoder.encode_type_reference(obj.type),
            'state': obj.state,
        }



def _save_state_impl(state: ProgramState) -> object:
    res: dict[str, object] = {}
    te = TypeEncoder()
    se = ProgramStateEncoder(te)

    globals = res['global-variables'] = {}
    for vstate in state.global_variables.values():
        globals[vstate.name] = se.encode_variable(vstate)

    res['expected-objects'] = list(state.expected_objects.keys())
    res['allow-object-reuse'] = state.allow_object_reuse

    objects = res['all-objects'] = {}
    for obj in state.objects.values():
        objects[obj.id] = se.encode_object(obj)

    return res


def save_state_to_string(state: ProgramState, *, compact: bool = False) -> str:
    return json.dumps(
        _save_state_impl(state),
        ensure_ascii=False,
        indent=None if compact else 4,
        separators=(',', ':' if compact else ': '),
        #sort_keys=True,  # keeping things git-friendly
    )

def save_state_to_file(state: ProgramState, file: object, *, compact: bool = False) -> None:
    json.dump(
        _save_state_impl(state),
        fp=file,
        ensure_ascii=False,
        indent=None if compact else 4,
        separators=(',', ':' if compact else ': '),
        #sort_keys=True,  # keeping things git-friendly
    )

