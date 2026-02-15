from datetime import timedelta
from time import time
from typing import final

from micro_svm.defect_detection import DefectAnalyzer, DetectedFailure
from micro_svm.global_context import CONTEXT as spec, show_compiled_specs
from micro_svm.serialization import save_state_to_file


from . import list_spec



# === FOR TESTING ===

show_compiled_specs(spec)
print('=================================================')

# === FOR TESTING ===



@final
class DefectHandler:
    def __init__(self, spec_origin: str):
        self._known_defects: set[str | None] = set()
        self._spec_origin = spec_origin


    def _show_compact(self, value: object) -> str:
        if isinstance(value, list):
            count = len(value)
            if count < 10:
                value = str(value)
            else:
                value = list({ repr(v) for v in value })
                value = value[:10]
                value = ', '.join(value)
                value = f"[{value}, ...]"
            return f"({count}) {value}"

        else:
            return str(value)


    def _sanitize_file_id(self, id: str) -> str:
        PRINTABLE_UNSAFE = '\\/:*?"<>|'
        return ''.join([
            c if (31 < ord(c) < 127) and c not in PRINTABLE_UNSAFE else '_' for c in id[:96]
        ])


    def process_defect(self, failure: DetectedFailure) -> None:
        if failure.failure_id not in self._known_defects:
            self._known_defects.add(failure.failure_id)

            for obj in failure.program_state.objects.values():
                print(obj.id, ':', obj.type, '=', self._show_compact(obj.state))

            filename = f"./{self._spec_origin}.[{self._sanitize_file_id(failure.failure_id)}].state.json"
            print(f'[i] Saving to "{filename}"...')
            with open(filename, 'wt', encoding='utf8') as f:
                save_state_to_file(failure.program_state, f)

            print('[i] Example:', failure.as_string(spec))



def main() -> None:
    handler = DefectHandler(list_spec.__spec__.name.replace('.', '/'))
    analyzer = DefectAnalyzer(spec)
    analyzer.on_defect = handler.process_defect

    ta = time()
    analyzer.analyze_function('std.List.equals')
    tb = time()

    if analyzer.defects_found == 0:
        print('[!] No valid failures were found')

    print(f"[i] Evaluation time: {timedelta(seconds=round(tb - ta))}")



if __name__ == '__main__':
    main()

