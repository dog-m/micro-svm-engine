import unittest

from micro_svm.cfg import ProgramVisualiser
from micro_svm.compiler import CompilerContext
from micro_svm.exploration import PathEnumerator, Program, ProgramPath
from micro_svm.global_context import GlobalContext
from micro_svm.type_hierarchy import TypeHierarchyResolver
from micro_svm.types import string

# === prerequisites ===


M = """<main>:
    Noop [comment='before']
    switch [cumulative=False]:
        PushPrimitive [value='my-string' (string)]
        case #0:
            condition:
                PushPrimitive [value='foo' (string)]
                PrimitiveOp [op=EQ, inputs=2]
            handler:
                Noop [comment='0']
        case #1:
            condition:
                PushPrimitive [value='bar' (string)]
                PrimitiveOp [op=EQ, inputs=2]
            handler:
                Noop [comment='1']
        case #2:
            condition:
                PushPrimitive [value='foo' (string)]
                PushPrimitive [value='bar' (string)]
                DistinctValues [count=3]
            handler:
                Noop [comment='2']
    Noop [comment='after']
    <marker: end-of-program>"""


PATHS = [
    """<path:0>
Noop [comment='before']
PushPrimitive [value='my-string' (string)]
PushPrimitive [value='foo' (string)]
PrimitiveOp [op=EQ, inputs=2]
Assume
ControlPoint [id='#|?0|']
Noop [comment='0']
Noop [comment='after']""",

    """<path:1>
Noop [comment='before']
PushPrimitive [value='my-string' (string)]
PushPrimitive [value='bar' (string)]
PrimitiveOp [op=EQ, inputs=2]
Assume
ControlPoint [id='#|?1|']
Noop [comment='1']
Noop [comment='after']""",

    """<path:2>
Noop [comment='before']
PushPrimitive [value='my-string' (string)]
PushPrimitive [value='foo' (string)]
PushPrimitive [value='bar' (string)]
DistinctValues [count=3]
Assume
ControlPoint [id='#|?2|']
Noop [comment='2']
Noop [comment='after']""",
]



# === testing ===


class Tests(unittest.TestCase):

    def build_program(self):
        cc = CompilerContext()
        cc.noop('before')

        cc.begin_switch(string, lambda: (
            cc.const('my-string', string)
        )).when('foo', lambda: (
            cc.noop('0'),
        )).when('bar', lambda: (
            cc.noop('1'),
        )).otherwise(lambda: (
            cc.noop('2'),
        )).end_switch()

        cc.noop('after')
        cc.end_of_program()
        return cc.build()


    def test_switch_structure(self):
        lines: list[str] = []
        vis = ProgramVisualiser(lines.append)
        vis.show('<main>', self.build_program().entry_node)

        self.maxDiff = None
        self.assertEqual(M, '\n'.join(lines))


    def test_switch_paths(self):
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
