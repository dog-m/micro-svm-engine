from collections import defaultdict

from .descriptors import structure_member_to_signature
from .global_context import GlobalContext


class TypeHierarchyResolver:
    def __init__(self, context: GlobalContext):
        self.subclasses: dict[str, set[str]] = {}  # immediate subclasses
        self.method_origin: dict[str, str] = {}    # mapping 'class.method -> implementation' (resolved)
        self.abstract_methods: set[str] = set()    # methods that are declared(!) having no implementation explicitly
        self.abstract_structures: set[str] = set() # classes that have any method resolved(!) to have no implementation
        self.root_structures: set[str] = set()
        #
        self._ctx = context
        self._field_origin: dict[str, str] = {}                   # mapping 'class.field -> class' (resolved)
        self._all_parents: dict[str, set[str]] = defaultdict(set) # mapping 'class -> all parents' (resolved)


    def reset(self) -> None:
        self.method_origin.clear()
        self.abstract_methods.clear()
        self.abstract_structures.clear()
        self.root_structures.clear()
        self._field_origin.clear()
        self._all_parents.clear()


    def _build_hierarchy(self) -> None:
        # find root classes and build the reverse of the known relationships (class -> parents => class -> subclasses)
        subs = self.subclasses = defaultdict(set)
        for sinfo in self._ctx.structures.values():
            sname = sinfo.structure_name
            if len(sinfo.parents) == 0:
                self.root_structures.add(sname)
            for parent in sinfo.parents:
                subs[parent].add(sname)

        # propagating parents level-by-level (BFS/BFT)
        queue = list(self.root_structures)
        visited = set()
        while queue:
            struct = queue.pop(0)
            sinfo = self._ctx.structures[struct]

            if struct not in visited:
                visited.add(struct)
            else:
                raise ValueError(f"Circular structure type dependency detected (seen '{struct}' already)")

            parents = self._all_parents[struct]
            parents.update(sinfo.parents)
            for parent in sinfo.parents:
                parents.update(self._all_parents[parent])

            queue.extend(self.subclasses[struct])


    def _abstract_pre_pass(self) -> None:
        for sinfo in self._ctx.structures.values():
            sname = sinfo.structure_name
            is_abstract_struct = False

            # set methods that already (not) have implementations
            for method in sinfo.methods:
                fsign = structure_member_to_signature(sname, method)
                if fsign in self._ctx.functions:
                    if self._ctx.functions[fsign].implementation is None:
                        self.abstract_methods.add(fsign)
                        is_abstract_struct = True
                    else:
                        self.method_origin[fsign] = fsign

            if is_abstract_struct:
                self.abstract_structures.add(sname)


    def _pull_method_origin(self, struct: str, method: str, visited: set[str]) -> str | None:
        if struct in visited:
            return None
        visited.add(struct)

        fsign = structure_member_to_signature(struct, method)
        if fsign in self.abstract_methods:
            return None

        origin = self.method_origin.get(fsign)
        if origin is not None:
            return origin

        # WARNING: using python-like method resolution here
        for parent in self._ctx.structures[struct].parents:
            origin = self._pull_method_origin(parent, method, visited)
            if origin is not None:
                self.method_origin[fsign] = origin
                return origin
        return None


    def _propagate_implementations(self) -> None:
        # this is a bit inefficient but I don't know any other simple ways around this
        for struct in self._ctx.structures.keys():
            # abstract methods will be absent here
            for _, (_, method) in self.get_all_methods(struct).items():
                _ = self._pull_method_origin(struct, method, set())


    def _abstract_post_pass(self) -> None:
        # resolve classes being abstract
        for sinfo in self._ctx.structures.values():
            sname = sinfo.structure_name
            if sname not in self.abstract_structures:
                for method in sinfo.methods:
                    fsign = structure_member_to_signature(sname, method)
                    if fsign not in self.method_origin:
                        self.abstract_structures.add(sname)
                        break


    def analyze_structure_hierarchy(self) -> None:
        self.reset()

        self._build_hierarchy()
        self._abstract_pre_pass()
        self._propagate_implementations()
        self._abstract_post_pass()
        # NOTE: will propagate fields on-demand (too much data to store)


    def get_virtual_call_targets(self, structure_name: str, method_name: str) -> dict[str, str]:
        """
        type_guard_name -> implementation_name
        """
        result: dict[str, str] = {}

        # traversing down the hierarchy in search of implementations
        queue: list[str] = [structure_name]
        visited: set[str] = set()
        while queue:
            struct = queue.pop()
            if struct in visited:
                continue
            visited.add(struct)

            # abstract classes cannot be instantiated thus cannot be (exact) type guards
            if struct not in self.abstract_structures:
                fsign = structure_member_to_signature(struct, method_name)
                if (implementation := self.method_origin.get(fsign)) is not None:
                    result[struct] = implementation

            queue.extend(self.subclasses[struct])

        return result


    def _pull_field_origin(self, struct: str, field: str, visited: set[str]) -> str | None:
        if struct in visited:
            return None
        visited.add(struct)

        fsign = structure_member_to_signature(struct, field)
        origin = self._field_origin.get(fsign)
        if origin is not None:
            return origin

        # checking parents first to ignore field re-declaration
        for parent in self._ctx.structures[struct].parents:
            origin = self._pull_field_origin(parent, field, visited)
            if origin is not None:
                self._field_origin[fsign] = origin
                return origin

        return struct if field in self._ctx.structures[struct].fields else None


    def get_field_origin(self, starting_struct: str, field: str) -> str:
        fsign = structure_member_to_signature(starting_struct, field)
        origin = self._field_origin.get(fsign)

        if origin is None:
            origin = self._field_origin[fsign] = self._pull_field_origin(starting_struct, field, set())
            if origin is None:
                raise ValueError(f"Unable to locate field '{field}' in '{starting_struct}'")

        return origin


    def get_all_parents_of(self, structure_name: str) -> set[str]:
        return self._all_parents[structure_name] if structure_name in self._all_parents else frozenset()


    def get_all_methods(self, structure_name: str) -> dict[str, tuple[str, str]]:
        """
        implementation_name -> [declaration_struct_name, method_name]
        """
        result: dict[str, tuple[str, str]] = {}

        visited_methods: set[str] = set()
        def collect_methods(parent_struct: str) -> None:
            for method_name, impl_name in self._ctx.structures[parent_struct].methods.items():
                if method_name not in visited_methods:
                    if self._ctx.functions[impl_name].implementation is not None:
                        visited_methods.add(method_name)  # each method has only a single implementation
                        result[impl_name] = (parent_struct, method_name)

        collect_methods(structure_name)
        for parent in self.get_all_parents_of(structure_name):
            collect_methods(parent)

        return result


    def get_all_fields(self, structure_name: str) -> dict[str, str]:
        """
        field_name -> origin_struct_name
        """
        result: dict[str, str] = {}

        for parent in [structure_name, *self.get_all_parents_of(structure_name)]:
            pclass = self._ctx.structures[parent]
            for field in pclass.fields.values():
                if field.name not in result:
                    result[field.name] = self.get_field_origin(pclass.structure_name, field.name)

        return result


