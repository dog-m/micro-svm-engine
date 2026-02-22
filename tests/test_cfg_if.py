import unittest

from micro_svm.cfg import ProgramVisualiser
from micro_svm.compiler import CompilerContext
from micro_svm.exploration import PathEnumerator, Program, ProgramPath
from micro_svm.global_context import GlobalContext
from micro_svm.type_hierarchy import TypeHierarchyResolver

# === prerequisites ===


N = 3
M = """<main>:
    if:
        PushPrimitive [value=1 (integer)]
    then:
        if:
            PushPrimitive [value=2 (integer)]
        then:
            if:
                PushPrimitive [value=3 (integer)]
            then:
                Noop
    Noop
    <marker: end-of-program>"""


PATHS = [
    """<path:0>
PushPrimitive [value=1 (integer)]
Assume
ControlPoint [id='#T']
PushPrimitive [value=2 (integer)]
Assume
ControlPoint [id='#TT']
PushPrimitive [value=3 (integer)]
Assume
ControlPoint [id='#TTT']
Noop
Noop""",

    """<path:1>
PushPrimitive [value=1 (integer)]
Assume
ControlPoint [id='#T']
PushPrimitive [value=2 (integer)]
Assume
ControlPoint [id='#TT']
PushPrimitive [value=3 (integer)]
PrimitiveOp [op=NOT, inputs=1]
Assume
ControlPoint [id='#TTF']
Noop""",

    """<path:2>
PushPrimitive [value=1 (integer)]
Assume
ControlPoint [id='#T']
PushPrimitive [value=2 (integer)]
PrimitiveOp [op=NOT, inputs=1]
Assume
ControlPoint [id='#TF']
Noop""",

    """<path:3>
PushPrimitive [value=1 (integer)]
PrimitiveOp [op=NOT, inputs=1]
Assume
ControlPoint [id='#F']
Noop""",
]



# === testing ===


class Tests(unittest.TestCase):

    def build_program(self):
        cc = CompilerContext()

        class Segment:
            def __init__(self, index: int, child: 'Segment | None' = None):
                self.index = index
                self.child = child

            def condition(self):
                return cc.const(self.index)

            def action(self) -> None:
                if self.child is None:
                    cc.noop()
                else:
                    self.child.assemble()

            def assemble(self) -> None:
                cc.branch(
                    self.condition
                ).when_true(
                    self.action
                ).explore_if()

        chain = None
        for i in range(N, 0, -1):
            chain = Segment(i, chain)
        chain.assemble()

        cc.noop()
        cc.end_of_program()
        return cc.build()


    def test_if_nested_structure(self):
        lines: list[str] = []
        vis = ProgramVisualiser(lines.append)
        vis.show('<main>', self.build_program().entry_node)

        self.maxDiff = None
        self.assertEqual(M, '\n'.join(lines))


    def test_if_nested_paths(self):
        spec = GlobalContext()
        prog = Program(spec, self.build_program())
        counter: list[ProgramPath] = []
        pe = PathEnumerator(prog, TypeHierarchyResolver(spec))
        pe.session_prefix = '#'
        pe.on_complete_path = lambda p, _: counter.append(p)
        pe.explore()

        self.assertEqual(len(PATHS), len(counter))

        for i, p in enumerate(counter):
            self.assertEqual(PATHS[i], p.get_trace(prefix=f'<path:{i}>\n'))




if __name__ == '__main__':
    unittest.main()
