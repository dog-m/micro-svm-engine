import unittest

from micro_svm.compiler import CompilerContext
from micro_svm.execution import SymbolicStateMachine, SymRefPolicy
from micro_svm.exploration import PathEnumerator, Program, ProgramPath
from micro_svm.global_context import GlobalContext
from micro_svm.type_hierarchy import TypeHierarchyResolver
from micro_svm.types import reference
from micro_svm.utils import simple_program

# === prerequisites ===


spec = GlobalContext()

spec.register_structure('my_exception_foo', [])
spec.register_structure('my_exception_bar', [])


def foo(cc: CompilerContext) -> None:
    cc.noop('foo')
    cc.try_block(lambda: (
        cc.noop('foo_throw'),
        cc.throw(cc.symbolic(reference)),
    )).catch('my_exception_foo', lambda e: (
        cc.noop('foo_catch'),
    )).explore()
    cc.noop('foo_end')

spec.register_function(
    name=foo.__name__,
    parameters=[],
    result=None,
    implementation=foo,
)


def bar(cc: CompilerContext) -> None:
    cc.noop('bar')
    cc.try_block(lambda: (
        cc.call(foo.__name__, [], None),
    )).catch('my_exception_bar', lambda e: (
        cc.noop('bar_catch'),
    )).final(lambda: (
        cc.noop('bar_final'),
    )).explore()
    cc.noop('bar_end')

spec.register_function(
    name=bar.__name__,
    parameters=[],
    result=None,
    implementation=bar,
)


th_resolver = TypeHierarchyResolver(spec)
th_resolver.analyze_structure_hierarchy()


PATHS_NORMAL = [
# main -> bar -> foo -> foo_throw (unknown_exception) -> bar_final (e=0) -> bar_end -> main_end
# [impossible] an unknown exception is raised but then also is expected to be non-existent when leaving the "final" block
(False, """
Noop [comment='main']
SubroutineEnter
Noop [comment='bar']
PushStackBoundary
SubroutineEnter
Noop [comment='foo']
PushStackBoundary
Noop [comment='foo_throw']
PushSymbolic [type=ref]
ExceptionWrite
ExceptionRead
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=EQ, inputs=2]
ExceptionRead
InstanceOf [struct=my_exception_foo, exact=False]
PrimitiveOp [op=OR, inputs=2]
ExceptionRead
InstanceOf [struct=my_exception_bar, exact=False]
PrimitiveOp [op=OR, inputs=2]
PrimitiveOp [op=NOT, inputs=1]
Assume
ControlPoint [id='<e:*>']
SubroutineExit
ClearStackToBoundary
Pop
ClearStackToBoundary
Pop
ExceptionRead
VariableWrite [dst=bar#~local1 (local)]
PushPrimitive [value=0 (ref)]
ExceptionWrite
Noop [comment='bar_final']
VariableRead [src=bar#~local1 (local)]
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=NEQ, inputs=2]
PrimitiveOp [op=NOT, inputs=1]
Assume
ControlPoint [id='<e:*>F']
Noop [comment='bar_end']
SubroutineExit
Noop [comment='main_end']
"""),

# main -> bar -> foo -> foo_throw (my_exception_bar) -> bar_catch -> bar_final (e=0) -> bar_end -> main_end
# [valid] normal operation, "bar" is thrown and then caught with an appropriate handler, leaving no "in-flight" exception
(True, """
Noop [comment='main']
SubroutineEnter
Noop [comment='bar']
PushStackBoundary
SubroutineEnter
Noop [comment='foo']
PushStackBoundary
Noop [comment='foo_throw']
PushSymbolic [type=ref]
ExceptionWrite
ExceptionRead
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=EQ, inputs=2]
ExceptionRead
InstanceOf [struct=my_exception_foo, exact=False]
PrimitiveOp [op=OR, inputs=2]
PrimitiveOp [op=NOT, inputs=1]
ExceptionRead
InstanceOf [struct=my_exception_bar, exact=False]
PrimitiveOp [op=AND, inputs=2]
Assume
ControlPoint [id='<e:my_exception_bar & !(my_exception_foo)>']
SubroutineExit
ClearStackToBoundary
Pop
ClearStackToBoundary
Pop
ExceptionRead
VariableWrite [dst=bar#~local0 (local)]
PushPrimitive [value=0 (ref)]
ExceptionWrite
Noop [comment='bar_catch']
ExceptionRead
VariableWrite [dst=bar#~local1 (local)]
PushPrimitive [value=0 (ref)]
ExceptionWrite
Noop [comment='bar_final']
VariableRead [src=bar#~local1 (local)]
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=NEQ, inputs=2]
PrimitiveOp [op=NOT, inputs=1]
Assume
ControlPoint [id='<e:my_exception_bar & !(my_exception_foo)>F']
Noop [comment='bar_end']
SubroutineExit
Noop [comment='main_end']
"""),

# main -> bar -> foo -> foo_throw (my_exception_foo) -> foo_catch -> foo_end -> bar_final (e=0) -> bar_end -> main_end
# [valid] normal operation, "foo" is thrown and then caught with a matching handler, leaving no "in-flight" exception
(True, """
Noop [comment='main']
SubroutineEnter
Noop [comment='bar']
PushStackBoundary
SubroutineEnter
Noop [comment='foo']
PushStackBoundary
Noop [comment='foo_throw']
PushSymbolic [type=ref]
ExceptionWrite
ExceptionRead
InstanceOf [struct=my_exception_foo, exact=False]
Assume
ControlPoint [id='<e:my_exception_foo>']
ClearStackToBoundary
Pop
ExceptionRead
VariableWrite [dst=foo#~local0 (local)]
PushPrimitive [value=0 (ref)]
ExceptionWrite
Noop [comment='foo_catch']
Noop [comment='foo_end']
SubroutineExit
ClearStackToBoundary
Pop
ExceptionRead
VariableWrite [dst=bar#~local1 (local)]
PushPrimitive [value=0 (ref)]
ExceptionWrite
Noop [comment='bar_final']
VariableRead [src=bar#~local1 (local)]
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=NEQ, inputs=2]
PrimitiveOp [op=NOT, inputs=1]
Assume
ControlPoint [id='<e:my_exception_foo>F']
Noop [comment='bar_end']
SubroutineExit
Noop [comment='main_end']
"""),
]


PATHS_FAILING = [
# main -> bar -> foo -> foo_throw (unknown_exception) -> bar_final (e!=0)
# [valid] normal operation, an unknown exception is thrown and then never caught (thou "final" is executed anyway)
(True, """
Noop [comment='main']
SubroutineEnter
Noop [comment='bar']
PushStackBoundary
SubroutineEnter
Noop [comment='foo']
PushStackBoundary
Noop [comment='foo_throw']
PushSymbolic [type=ref]
ExceptionWrite
ExceptionRead
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=EQ, inputs=2]
ExceptionRead
InstanceOf [struct=my_exception_foo, exact=False]
PrimitiveOp [op=OR, inputs=2]
ExceptionRead
InstanceOf [struct=my_exception_bar, exact=False]
PrimitiveOp [op=OR, inputs=2]
PrimitiveOp [op=NOT, inputs=1]
Assume
ControlPoint [id='<e:*>']
SubroutineExit
ClearStackToBoundary
Pop
ClearStackToBoundary
Pop
ExceptionRead
VariableWrite [dst=bar#~local1 (local)]
PushPrimitive [value=0 (ref)]
ExceptionWrite
Noop [comment='bar_final']
VariableRead [src=bar#~local1 (local)]
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=NEQ, inputs=2]
Assume
ControlPoint [id='<e:*>T']
VariableRead [src=bar#~local1 (local)]
ExceptionWrite
ExceptionRead
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=EQ, inputs=2]
PrimitiveOp [op=NOT, inputs=1]
Assume
"""),

# main -> bar -> foo -> foo_throw (my_exception_bar) -> bar_catch -> bar_final (e!=0)
# [impossible] a known exception is thrown and then properly caught but an exception is still expected to be "flying-through"
(False, """
Noop [comment='main']
SubroutineEnter
Noop [comment='bar']
PushStackBoundary
SubroutineEnter
Noop [comment='foo']
PushStackBoundary
Noop [comment='foo_throw']
PushSymbolic [type=ref]
ExceptionWrite
ExceptionRead
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=EQ, inputs=2]
ExceptionRead
InstanceOf [struct=my_exception_foo, exact=False]
PrimitiveOp [op=OR, inputs=2]
PrimitiveOp [op=NOT, inputs=1]
ExceptionRead
InstanceOf [struct=my_exception_bar, exact=False]
PrimitiveOp [op=AND, inputs=2]
Assume
ControlPoint [id='<e:my_exception_bar & !(my_exception_foo)>']
SubroutineExit
ClearStackToBoundary
Pop
ClearStackToBoundary
Pop
ExceptionRead
VariableWrite [dst=bar#~local0 (local)]
PushPrimitive [value=0 (ref)]
ExceptionWrite
Noop [comment='bar_catch']
ExceptionRead
VariableWrite [dst=bar#~local1 (local)]
PushPrimitive [value=0 (ref)]
ExceptionWrite
Noop [comment='bar_final']
VariableRead [src=bar#~local1 (local)]
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=NEQ, inputs=2]
Assume
ControlPoint [id='<e:my_exception_bar & !(my_exception_foo)>T']
VariableRead [src=bar#~local1 (local)]
ExceptionWrite
ExceptionRead
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=EQ, inputs=2]
PrimitiveOp [op=NOT, inputs=1]
Assume
"""),

# main -> bar -> foo -> foo_throw (my_exception_foo) -> foo_catch -> foo_end -> bar_final (e!=0)
# [impossible] a known exception is thrown and then properly caught but an exception is still expected to be "flying-through"
(False, """
Noop [comment='main']
SubroutineEnter
Noop [comment='bar']
PushStackBoundary
SubroutineEnter
Noop [comment='foo']
PushStackBoundary
Noop [comment='foo_throw']
PushSymbolic [type=ref]
ExceptionWrite
ExceptionRead
InstanceOf [struct=my_exception_foo, exact=False]
Assume
ControlPoint [id='<e:my_exception_foo>']
ClearStackToBoundary
Pop
ExceptionRead
VariableWrite [dst=foo#~local0 (local)]
PushPrimitive [value=0 (ref)]
ExceptionWrite
Noop [comment='foo_catch']
Noop [comment='foo_end']
SubroutineExit
ClearStackToBoundary
Pop
ExceptionRead
VariableWrite [dst=bar#~local1 (local)]
PushPrimitive [value=0 (ref)]
ExceptionWrite
Noop [comment='bar_final']
VariableRead [src=bar#~local1 (local)]
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=NEQ, inputs=2]
Assume
ControlPoint [id='<e:my_exception_foo>T']
VariableRead [src=bar#~local1 (local)]
ExceptionWrite
ExceptionRead
PushPrimitive [value=0 (ref)]
PrimitiveOp [op=EQ, inputs=2]
PrimitiveOp [op=NOT, inputs=1]
Assume
"""),
]


# === testing ===


class Tests(unittest.TestCase):

    def test_try_catch_finally(self):
        self.maxDiff = None
        paths_normal: list[ProgramPath] = []
        paths_failing: list[ProgramPath] = []

        #show_compiled_specs(spec)

        def main(cc: CompilerContext) -> None:
            cc.noop('main')
            cc.call(bar.__name__, [], None)
            cc.noop('main_end')

        sub = simple_program(spec, main)
        pe = PathEnumerator(Program(spec, sub), th_resolver)
        pe.on_complete_path = lambda pp, _: paths_normal.append(pp)
        pe.on_failing_path  = lambda pp, pe, msg, stack: paths_failing.append(pp)
        pe.explore()

        #print('[!]', len(paths_normal), '+', len(paths_failing))
        self.assertEqual(len(paths_normal),  len(PATHS_NORMAL))
        self.assertEqual(len(paths_failing), len(PATHS_FAILING))

        for i, p in enumerate(paths_normal):
            expected_runnable, expected_trace = PATHS_NORMAL[i]

            self.assertEqual(expected_trace, p.get_trace(prefix='\n', suffix='\n'))

            m = SymbolicStateMachine(spec, th_resolver, solver_timeout=1000)
            m.config.symbolic_ref_policy = SymRefPolicy.OPEN
            res = m.execute(p.instructions())
            #m.show_expressions()

            expectation = 'executable' if expected_runnable else 'not executable'
            self.assertEqual(expected_runnable, res, f"Normal path #{i} failed to be {expectation}")

        for i, p in enumerate(paths_failing):
            expected_runnable, expected_trace = PATHS_FAILING[i]

            self.assertEqual(expected_trace, p.get_trace(prefix='\n', suffix='\n'))

            m = SymbolicStateMachine(spec, th_resolver, solver_timeout=1000)
            m.config.symbolic_ref_policy = SymRefPolicy.OPEN
            res = m.execute(p.instructions(), flush=True)
            #m.show_expressions()

            expectation = 'executable' if expected_runnable else 'not executable'
            self.assertEqual(expected_runnable, res, f"Failing path #{i} failed to be {expectation}")




if __name__ == '__main__':
    unittest.main()
