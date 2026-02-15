from typing import Callable

from .compiler import CompilerContext
from .descriptors import CompiledSubroutine
from .global_context import GlobalContext
from .types import TypeInfo, ref



def simple_program(ctx: GlobalContext, implementation: Callable[[CompilerContext], None]) -> CompiledSubroutine:
    cc = CompilerContext()

    implementation(cc)

    cc.end_of_program()
    sub = cc.build()

    for lv in sub.local_variables:
        ctx.register_symbol(lv)
    return sub



def _empty_ctor_impl(_: CompilerContext) -> None:
    pass


def register_empty_constructor(
        ctx: GlobalContext,
        structure_name: str,
        *,
        ctor_name: str = '<ctor>',
        params_extra: list[tuple[str, TypeInfo]] | None = None,
        parent: str | None = None,
    ) -> None:
    if params_extra is None:
        params_extra = []

    impl = _empty_ctor_impl
    if parent is not None:
        # WARNING: expecting the same constructor signature for the parent!
        def _non_empty_ctor(cc: CompilerContext) -> None:
            args = [
                cc.get_parameter(pname).r
                for pname in cc.current_function.parameters.keys()
            ]
            cc.call((parent, ctor_name), args, None, virtual=False)

        impl = _non_empty_ctor

    ctx.register_function(
        name=ctor_name,
        parameters=[
            ('this', ref(ctx.structures[structure_name])),
            *params_extra,
        ],
        result=None,
        implementation=impl,  # every non-abstract class should have a constructor!
        structure=structure_name,
    )

