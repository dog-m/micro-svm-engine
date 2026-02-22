import unittest

from micro_svm.compiler import CompilerContext
from micro_svm.execution import SymbolicStateMachine
from micro_svm.exploration import PathEnumerator, Program, ProgramPath
from micro_svm.global_context import GlobalContext
from micro_svm.type_hierarchy import TypeHierarchyResolver
from micro_svm.types import field, integer, ref, reference
from micro_svm.utils import simple_program

# === prerequisites ===


X_INITIAL = 2
X_CHANGED = 5

spec = GlobalContext()
spec.register_structure('A', [], [ field('x', integer), ])
spec.register_structure('B', ['A'], [])

spec.register_function(
    name='<ctor>',
    parameters=[
        ('this', ref(spec.structures['A'])),
    ],
    result=None,
    implementation=lambda ctx: (
        ctx.field_write(ctx.get_parameter('this').r, 'A', 'x', ctx.const(X_INITIAL)),
    ),
    structure='A',
)

spec.register_function(
    name='<ctor>',
    parameters=[
        ('this', ref(spec.structures['B'])),
    ],
    result=None,
    implementation=lambda ctx: (
        # WARNING: every class should have a constructor!
        ctx.call(('A', '<ctor>'), [ctx.get_parameter('this').r], None, virtual=False),
    ),
    structure='B',
)

th_resolver = TypeHierarchyResolver(spec)
th_resolver.analyze_structure_hierarchy()



# === testing ===


class Tests(unittest.TestCase):

    def test_object_instantiation_and_field_access(self):
        paths: list[ProgramPath] = []

        def main(cc: CompilerContext) -> None:
            obj = cc.make_local_variable(reference)
            cc.write(obj.w, cc.new_instance('B', '<ctor>', []))
            cc.assume(cc.instance_of(obj.r, 'A'))
            cc.assume(cc.instance_of(obj.r, 'B'))
            # checking value after initialization by the constructor
            cc.assume(cc.field_read(obj.r, 'B', 'x') == cc.const(X_INITIAL))
            # checking the field can be updated
            cc.field_write(obj.r, 'B', 'x', cc.const(X_CHANGED))
            cc.assume(cc.field_read(obj.r, 'B', 'x') == cc.const(X_CHANGED))

        sub = simple_program(spec, main)
        pe = PathEnumerator(Program(spec, sub), th_resolver)
        pe.on_complete_path = lambda pp, _: paths.append(pp)
        pe.explore()
        for p in paths:
            m = SymbolicStateMachine(spec, th_resolver, solver_timeout=1000)
            res = m.execute(p.instructions())
            self.assertTrue(res)


    def test_object_field_not_symbolic(self):
        paths: list[ProgramPath] = []

        def failing_main(cc: CompilerContext) -> None:
            obj = cc.make_local_variable(reference)
            cc.write(obj.w, cc.new_instance('B', '<ctor>', []))
            cc.assume(cc.field_read(obj.r, 'B', 'x') == cc.const(X_INITIAL + 1))

        sub = simple_program(spec, failing_main)
        pe = PathEnumerator(Program(spec, sub), th_resolver)
        pe.on_complete_path = lambda pp, _: paths.append(pp)
        pe.explore()
        for p in paths:
            m = SymbolicStateMachine(spec, th_resolver, solver_timeout=1000)
            res = m.execute(p.instructions())
            self.assertFalse(res)




if __name__ == '__main__':
    unittest.main()
