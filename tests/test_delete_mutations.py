import ast

import pytest

from pymut4se.model import CodeChunk, Module
from pymut4se.mutation import generate_mutants
from pymut4se.mutation.generic import (
    DeleteAssignmentMutation,
    DeleteIfStatementMutation,
    DeleteReturnMutation,
    DeleteWhileMutation,
)


def _chunk(source: str, *, start_line: int = 1) -> CodeChunk:
    return CodeChunk(
        source,
        "module",
        "example",
        "function",
        start_line,
        start_line + len(source.splitlines()) - 1,
    )


def _assert_valid(mutants: list[CodeChunk], mutation_type: str) -> None:
    assert mutants
    for mutant in mutants:
        ast.parse(mutant.code)
        compile(mutant.code, "<delete-mutant>", "exec")
        assert mutant.mutation_type == mutation_type
        assert mutant.parent is not None


def test_delete_assignment_handles_regular_annotated_and_augmented_assignments() -> None:
    original = _chunk(
        "def update(value):\n    total = 1\n    count: int = 2\n    total += count\n    return total\n",
        start_line=10,
    )

    mutants = DeleteAssignmentMutation().mutate(original)

    assert len(mutants) == 3
    assert {mutant.mutation_operator for mutant in mutants} == {"Assign", "AnnAssign", "AugAssign"}
    assert {mutant.line_changed for mutant in mutants} == {11, 12, 13}
    for mutant in mutants:
        assignments = [
            node
            for node in ast.walk(ast.parse(mutant.code))
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        ]
        assert len(assignments) == 2
    _assert_valid(mutants, "delete_assignment")


def test_delete_if_removes_the_complete_statement_and_else_branch() -> None:
    original = _chunk("def choose(flag):\n    if flag:\n        return 1\n    else:\n        return 2\n    return 3\n")

    mutants = DeleteIfStatementMutation().mutate(original)

    assert len(mutants) == 1
    assert not any(isinstance(node, ast.If) for node in ast.walk(ast.parse(mutants[0].code)))
    assert mutants[0].mutation_operator == "If"
    _assert_valid(mutants, "delete_if_statement")


def test_delete_while_removes_the_complete_loop_and_else_branch() -> None:
    original = _chunk(
        "def consume(items):\n"
        "    while items:\n"
        "        items.pop()\n"
        "    else:\n"
        "        items.append(0)\n"
        "    return items\n"
    )

    mutants = DeleteWhileMutation().mutate(original)

    assert len(mutants) == 1
    assert not any(isinstance(node, ast.While) for node in ast.walk(ast.parse(mutants[0].code)))
    assert mutants[0].mutation_operator == "While"
    _assert_valid(mutants, "delete_while")


def test_delete_return_mutates_each_return_independently_and_repairs_nested_bodies() -> None:
    original = _chunk("def choose(flag):\n    if flag:\n        return 1\n    return 2\n")

    mutants = DeleteReturnMutation().mutate(original)

    assert len(mutants) == 2
    assert all(
        sum(isinstance(node, ast.Return) for node in ast.walk(ast.parse(mutant.code))) == 1 for mutant in mutants
    )
    assert any(isinstance(node, ast.Pass) for mutant in mutants for node in ast.walk(ast.parse(mutant.code)))
    _assert_valid(mutants, "delete_return")


@pytest.mark.parametrize(
    ("operator", "source", "mutation_type"),
    [
        (DeleteAssignmentMutation(), "def f():\n    value = 1\n", "delete_assignment"),
        (DeleteIfStatementMutation(), "def f(flag):\n    if flag:\n        return 1\n", "delete_if_statement"),
        (DeleteWhileMutation(), "def f(flag):\n    while flag:\n        break\n", "delete_while"),
        (DeleteReturnMutation(), "def f():\n    return 1\n", "delete_return"),
    ],
)
def test_deletion_repairs_an_empty_function_body(operator, source: str, mutation_type: str) -> None:
    mutants = operator.mutate(_chunk(source))

    assert len(mutants) == 1
    function = ast.parse(mutants[0].code).body[0]
    assert isinstance(function, ast.FunctionDef)
    assert len(function.body) == 1
    assert isinstance(function.body[0], ast.Pass)
    _assert_valid(mutants, mutation_type)


def test_deletion_repairs_try_and_finally_bodies() -> None:
    original = _chunk("def guarded():\n    try:\n        return 1\n    finally:\n        cleanup = True\n")

    assignment_mutant = DeleteAssignmentMutation().mutate(original)[0]
    return_mutant = DeleteReturnMutation().mutate(original)[0]

    compile(assignment_mutant.code, "<assignment-mutant>", "exec")
    compile(return_mutant.code, "<return-mutant>", "exec")


def test_delete_operators_integrate_with_generation_and_orm_relationships() -> None:
    module = Module("example", "example.py")
    source = (
        "def process(flag):\n"
        "    value = 1\n"
        "    if flag:\n"
        "        return value\n"
        "    while flag:\n"
        "        flag = False\n"
        "    return value\n"
    )
    original = CodeChunk(source, module.module_id, "process", "function", 1, 7)
    module.code_chunks.append(original)

    mutants = generate_mutants(
        module,
        [DeleteAssignmentMutation, DeleteIfStatementMutation, DeleteWhileMutation, DeleteReturnMutation],
        max_degree=1,
    )

    assert len(mutants) == 6
    assert {mutant.mutation_type for mutant in mutants} == {
        "delete_assignment",
        "delete_if_statement",
        "delete_while",
        "delete_return",
    }
    assert all(mutant.module is module for mutant in mutants)
    assert all(mutant.parent is original for mutant in mutants)
