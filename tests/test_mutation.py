from ast import AST
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.model import Base, CodeChunk, Module, Package, Project
from pymut4se.mutation import Mutation, PythonASTMutation, build_mutated_code_chunk, generate_mutants


class AppendMarkerMutation(Mutation):
    def _parse(self, code: CodeChunk) -> str:
        return code.code

    def _find_mutation_points(self, parsed_code: Any) -> list:
        return [len(parsed_code)]

    def _apply_mutation(self, code: CodeChunk, parsed_code: Any, mutation_point: list) -> list[CodeChunk]:
        mutated_code = f"{parsed_code.rstrip()}\nmutation_marker = {code.mutation_degree + 1}\n"
        return [
            build_mutated_code_chunk(
                original=code,
                mutated_code=mutated_code,
                relative_line_changed=1,
                relative_column_changed=0,
                mutation_type="comment",
                mutation_operator=type(self).__name__,
            )
        ]


class InspectASTMutation(PythonASTMutation):
    parsed: AST | None = None

    def _find_mutation_points(self, parsed_code: Any) -> list:
        self.parsed = parsed_code
        return []

    def _apply_mutation(self, code: CodeChunk, parsed_code: Any, mutation_point: list) -> list[CodeChunk]:
        return []


def _project_graph() -> tuple[Project, Package, Module, CodeChunk]:
    package = Package("demo", "demo")
    module = Module("demo.example", "demo/example.py", package.package_id)
    chunk = CodeChunk("def execute():\n    return True\n", module.module_id, "execute", "function", 5, 6)
    package.modules.append(module)
    module.code_chunks.append(chunk)
    project = Project("demo", ".", packages=[package], modules=[module], code_chunks=[chunk])
    return project, package, module, chunk


def test_generate_mutants_connects_multiple_degrees_to_the_orm_graph() -> None:
    project, _, module, original = _project_graph()

    mutants = generate_mutants(module, [AppendMarkerMutation], max_degree=2)

    assert [mutant.mutation_degree for mutant in mutants] == [1, 2]
    assert mutants[0].parent is original
    assert mutants[1].parent is mutants[0]
    assert all(mutant.original is original for mutant in mutants)
    assert original.derived_chunks == mutants
    assert all(mutant.module is module for mutant in mutants)
    assert all(mutant.project is project for mutant in mutants)
    assert module.code_chunks == [original, *mutants]
    assert project.code_chunks == [original, *mutants]


def test_generate_mutants_for_package_includes_descendants_and_ignores_existing_mutants() -> None:
    parent = Package("demo", "demo")
    child = Package("demo.child", "demo/child", parent_id=parent.package_id)
    module = Module("demo.child.example", "demo/child/example.py", child.package_id)
    original = CodeChunk("def f():\n    return 1\n", module.module_id, "f", "function", 1, 2)
    existing_mutant = build_mutated_code_chunk(original, "def f():\n    return 2\n", 2, 4, "return", "manual")
    parent.children.append(child)
    child.modules.append(module)
    module.code_chunks.extend([original, existing_mutant])

    mutants = generate_mutants(parent, [AppendMarkerMutation(), AppendMarkerMutation], max_degree=1)

    assert len(mutants) == 1
    assert mutants[0].parent is original


def test_build_mutated_chunk_preserves_context_and_change_location() -> None:
    project, _, module, original = _project_graph()

    mutant = build_mutated_code_chunk(
        original,
        "def execute():\n    return False\n",
        relative_line_changed=2,
        relative_column_changed=4,
        mutation_type="boolean",
        mutation_operator="replace_true",
    )

    assert mutant.module is module
    assert mutant.project is project
    assert mutant.parent is original
    assert mutant.original is original
    assert mutant.original_id == original.chunk_id
    assert original.original is None
    assert mutant.line_changed == 6
    assert mutant.column_changed == 5
    assert mutant.mutation_degree == 1


def test_mutants_persist_by_adding_only_the_existing_project() -> None:
    project, _, module, _ = _project_graph()
    mutants = generate_mutants(module, [AppendMarkerMutation], max_degree=2)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(project)
        session.commit()
        session.expire_all()

        stored_module = session.get(Module, module.module_id)
        assert stored_module is not None
        assert {chunk.chunk_id for chunk in stored_module.code_chunks} == {
            chunk.chunk_id for chunk in [*mutants, module.code_chunks[0]]
        }


def test_zero_degree_and_empty_targets_produce_no_mutants() -> None:
    module = Module("empty", "empty.py")
    assert generate_mutants(module, [AppendMarkerMutation], max_degree=1) == []
    original = CodeChunk("def f(): pass", module.module_id, "f", "function", 1, 1)
    assert generate_mutants(original, [AppendMarkerMutation], max_degree=0) == []


def test_python_ast_mutation_dedents_method_chunks() -> None:
    chunk = CodeChunk("    def method(self):\n        return True\n", "module", "Class.method", "function", 1, 2)
    operator = InspectASTMutation()

    assert operator.mutate(chunk) == []
    assert operator.parsed is not None
