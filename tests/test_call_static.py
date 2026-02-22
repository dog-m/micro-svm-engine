import unittest

import z3

from micro_svm.compiler import CompilerContext
from micro_svm.execution import SymbolicStateMachine
from micro_svm.exploration import PathEnumerator, Program, ProgramPath
from micro_svm.global_context import GlobalContext
from micro_svm.type_hierarchy import TypeHierarchyResolver
from micro_svm.types import integer
from micro_svm.utils import simple_program

# === prerequisites ===


spec = GlobalContext()

spec.register_function(
    name='foo',
    parameters=[
    ],
    result=integer,
    implementation=lambda ctx: (
        ctx.write(ctx.get_function_result().w, ctx.const(5)),
    ),
)

spec.register_function(
    name='bar',
    parameters=[
    ],
    result=integer,
    implementation=lambda ctx: (
        ctx.write(ctx.get_function_result().w, ctx.const(7)),
    ),
)

th_resolver = TypeHierarchyResolver(spec)
th_resolver.analyze_structure_hierarchy()


EXPRESSIONS = [
    '64 == (#0)<main>#~local0:0',
    '5 == (#1)foo#~result:1',
    '5 == (#0)<main>#~local1:1',             # <=> '(#0)<main>#~local1:1 == (#1)foo#~result:1'
    '7 == (#1)bar#~result:1',
    '7 == (#0)<main>#~local2:1',             # <=> '(#0)<main>#~local2:1 == (#1)bar#~result:1'
    '(#0)<main>#~local0:0 == 11*5 + 2 + 7',  # <=> '(#0)<main>#~local0:0 == 11*(#0)<main>#~local1:1 + 2 + (#0)<main>#~local2:1',
    '5 == (#1)foo#~result:2',
    '5 == (#0)<main>#~local3:1',             # <=> '(#0)<main>#~local3:1 == (#1)foo#~result:2',
    '7 == (#1)bar#~result:2',
    '7 == (#0)<main>#~local4:1',             # <=> '(#0)<main>#~local4:1 == (#1)bar#~result:2',
    '11*5 + 2 + 7 == (#0)<main>#~local0:0',  # <=> '11*(#0)<main>#~local3:1 + 2 + (#0)<main>#~local4:1 == (#0)<main>#~local0:0',
]


# === testing ===


class Tests(unittest.TestCase):

    def test_static_call(self):
        self.maxDiff = None
        paths: list[ProgramPath] = []

        def main(cc: CompilerContext) -> None:
            handle = cc.make_local_variable(integer)
            cc.assume(handle.r == cc.const(11 * 5 + 2 + 7))
            # ---
            cc.assume(handle.r == (cc.const(11) * cc.call('foo', [], integer) + cc.const(2) + cc.call('bar', [], integer)))
            cc.assume((cc.const(11) * cc.call('foo', [], integer) + cc.const(2) + cc.call('bar', [], integer)) == handle.r)

        sub = simple_program(spec, main)
        pe = PathEnumerator(Program(spec, sub), th_resolver)
        pe.on_complete_path = lambda pp, _: paths.append(pp)
        pe.explore()
        self.assertEqual(1, len(paths))

        m = SymbolicStateMachine(spec, th_resolver, solver_timeout=1000)
        # prepare initialization expressions for separating the out later
        m._init_symbols()
        baseline_expr_count = len(m._expressions)

        is_executable = m.execute(paths[0].instructions())

        self.assertTrue(is_executable)
        self.assertEqual(len(EXPRESSIONS), len(m._expressions) - baseline_expr_count)

        z3.set_pp_option('bounded', False)
        z3.set_pp_option('max_width', 1000)
        self.assertEqual('\n'.join(EXPRESSIONS), '\n'.join(
            str(e)
            for e in m._expressions[baseline_expr_count:]
        ))




if __name__ == '__main__':
    unittest.main()
