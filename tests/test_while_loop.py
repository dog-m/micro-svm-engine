import unittest

from micro_svm.compiler import CompilerContext
from micro_svm.exploration import PathEnumerator, Program, ProgramPath
from micro_svm.global_context import GlobalContext
from micro_svm.type_hierarchy import TypeHierarchyResolver
from micro_svm.types import boolean
from micro_svm.utils import simple_program

# === prerequisites ===


PATHS = """
VariableRead [src=foo (global)]
PrimitiveOp [op=NOT, inputs=1]
Assume
ControlPoint [id='#F']
---------------------
VariableRead [src=foo (global)]
Assume
ControlPoint [id='#T']
Noop [comment='loop-body-here']
VariableRead [src=foo (global)]
PrimitiveOp [op=NOT, inputs=1]
Assume
ControlPoint [id='#TF']
---------------------
VariableRead [src=foo (global)]
Assume
ControlPoint [id='#T']
Noop [comment='loop-body-here']
VariableRead [src=foo (global)]
Assume
ControlPoint [id='#TT']
Noop [comment='loop-body-here']
VariableRead [src=foo (global)]
PrimitiveOp [op=NOT, inputs=1]
Assume
ControlPoint [id='#TTF']
---------------------
VariableRead [src=foo (global)]
Assume
ControlPoint [id='#T']
Noop [comment='loop-body-here']
VariableRead [src=foo (global)]
Assume
ControlPoint [id='#TT']
Noop [comment='loop-body-here']
VariableRead [src=foo (global)]
Assume
ControlPoint [id='#TTT']
Noop [comment='loop-body-here']
VariableRead [src=foo (global)]
PrimitiveOp [op=NOT, inputs=1]
Assume
ControlPoint [id='#TTTF']
""".split('---------------------')


# === testing ===


class WL(unittest.TestCase):
    def test_foo(self):
        spec = GlobalContext()
        spec.register_global_variable('foo', boolean, initializer=False)
        paths: list[ProgramPath] = []

        def main(cc: CompilerContext) -> None:
            foo = cc.get_global_variable('foo')
            # ===
            cc.branch(lambda: (
                foo.r
            )).when_true(lambda: (
                cc.noop('loop-body-here'),
            )).explore_while()

        sub = simple_program(spec, main)
        th_resolver = TypeHierarchyResolver(spec)
        pe = PathEnumerator(Program(spec, sub), th_resolver)
        pe.on_complete_path = lambda pp, _: paths.append(pp)
        pe.session_prefix = '#'
        pe.config.loop_max_iter_count = 3
        pe.explore()
        self.assertEqual(len(paths), len(PATHS))

        for i, p in enumerate(paths):
            self.assertEqual(PATHS[i], p.get_trace(prefix='\n', suffix='\n'))




if __name__ == '__main__':
    unittest.main()
