import unittest

from micro_svm.compiler import CompilerContext
from micro_svm.execution import SymbolicStateMachine
from micro_svm.exploration import PathEnumerator, Program, ProgramPath
from micro_svm.global_context import GlobalContext
from micro_svm.type_hierarchy import TypeHierarchyResolver
from micro_svm.types import integer, ref, reference
from micro_svm.utils import register_empty_constructor, simple_program

# === prerequisites ===

"""
class A:
    foo(x) = ...

class B:
    foo(x) = ...
    bar()  = None

class C:
    bar() = ...
"""


spec = GlobalContext()
spec.register_structure('A', [],    [])
spec.register_structure('B', ['A'], [])
spec.register_structure('C', ['B'], [])

register_empty_constructor(spec, 'A')
register_empty_constructor(spec, 'C')

def _debug_method_impl(cc: CompilerContext) -> None:
    cc.noop(f"Hello from {cc.current_function.full_name}")

# A.foo
spec.register_function(
    name='foo',
    parameters=[
        ('this', ref(spec.structures['A'])),
        ('x', integer),  # this is here to text correct argument passing, there would be 0/NULL
    ],
    result=None,
    implementation=_debug_method_impl,
    structure='A',
)

# B.foo
spec.register_function(
    name='foo',
    parameters=[
        ('this', ref(spec.structures['B'])),
        ('x', integer),
    ],
    result=None,
    implementation=_debug_method_impl,
    structure='B',
)

# B.bar
spec.register_function(
    name='bar',
    parameters=[
        ('this', ref(spec.structures['B'])),
    ],
    result=None,
    implementation=None,
    structure='B',
)

# C.bar
spec.register_function(
    name='bar',
    parameters=[
        ('this', ref(spec.structures['C'])),
    ],
    result=None,
    implementation=_debug_method_impl,
    structure='C',
)

th_resolver = TypeHierarchyResolver(spec)
th_resolver.analyze_structure_hierarchy()


PATHS = [
# trying to call 'C.foo' on 'C' expecting 'C'
(True, """
NewInstance [type=C]
Copy [count=1, pos=0]
SubroutineEnter
VariableWrite [dst=C.<ctor>#this (local)]
SubroutineExit
VariableWrite [dst=<main>#~local0 (local)]
VariableRead [src=<main>#~local0 (local)]
PushPrimitive [value=0 (integer)]
Copy [count=1, pos=1]
InstanceOf [struct=C, exact=True]
Assume
ControlPoint [id='|1|']
SubroutineEnter
VariableWrite [dst=B.foo#x (local)]
VariableWrite [dst=B.foo#this (local)]
Noop [comment='Hello from B.foo']
SubroutineExit
"""),

# trying to call 'A.foo' on 'C' expecting 'A'
(False, """
NewInstance [type=C]
Copy [count=1, pos=0]
SubroutineEnter
VariableWrite [dst=C.<ctor>#this (local)]
SubroutineExit
VariableWrite [dst=<main>#~local0 (local)]
VariableRead [src=<main>#~local0 (local)]
PushPrimitive [value=0 (integer)]
Copy [count=1, pos=1]
InstanceOf [struct=A, exact=True]
Assume
ControlPoint [id='|0|']
SubroutineEnter
VariableWrite [dst=A.foo#x (local)]
VariableWrite [dst=A.foo#this (local)]
Noop [comment='Hello from A.foo']
SubroutineExit
"""),
]


# === testing ===


class VC(unittest.TestCase):
    def test_virtual_call(self):
        self.maxDiff = None
        paths: list[ProgramPath] = []

        def main(cc: CompilerContext) -> None:
            obj = cc.make_local_variable(reference)
            cc.write(obj.w, cc.new_instance('C', '<ctor>', []))
            cc.call(('A', 'foo'), [obj.r, cc.const(0)], None)

        sub = simple_program(spec, main)
        pe = PathEnumerator(Program(spec, sub), th_resolver)
        pe.on_complete_path = lambda pp, _: paths.append(pp)
        pe.explore()
        self.assertEqual(len(PATHS), len(paths))

        for i, p in enumerate(paths):
            expected_runnable, expected_trace = PATHS[i]

            self.assertEqual(expected_trace, p.get_trace(prefix='\n', suffix='\n'))

            m = SymbolicStateMachine(spec, th_resolver, solver_timeout=1000)
            runnable = m.execute(p.instructions())

            self.assertEqual(expected_runnable, runnable)




if __name__ == '__main__':
    unittest.main()
