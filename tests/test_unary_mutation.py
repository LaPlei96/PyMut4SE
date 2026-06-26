import ast

from pymut4se.model import CodeChunk, Module
from pymut4se.mutation import generate_mutants
from pymut4se.mutation.generic import UnaryMutation


def _chunk(source: str, *, start_line: int = 1) -> CodeChunk:
    return CodeChunk(
        source,
        "module",
        "example",
        "function",
        start_line,
        start_line + len(source.splitlines()) - 1,
    )


def _operator_names(source: str) -> list[str]:
    return [type(node.op).__name__ for node in ast.walk(ast.parse(source)) if isinstance(node, ast.UnaryOp)]


def test_replaces_a_unary_operator_with_each_alternative() -> None:
    original = _chunk("def negate(value):\n    return -value\n", start_line=10)

    mutants = UnaryMutation().mutate(original)

    assert len(mutants) == 3
    assert {mutant.mutation_operator for mutant in mutants} == {"Invert", "Not", "UAdd"}
    assert {_operator_names(mutant.code)[0] for mutant in mutants} == {"Invert", "Not", "UAdd"}
    assert {mutant.mutation_type for mutant in mutants} == {"unary"}
    assert {mutant.line_changed for mutant in mutants} == {11}
    assert {mutant.column_changed for mutant in mutants} == {12}


def test_mutates_only_one_of_multiple_unary_expressions_per_mutant() -> None:
    original = _chunk("def combine(left, right):\n    return -left + +right\n")
    original_operators = _operator_names(original.code)

    mutants = UnaryMutation().mutate(original)

    assert len(mutants) == 6
    for mutant in mutants:
        mutated_operators = _operator_names(mutant.code)
        differences = sum(before != after for before, after in zip(original_operators, mutated_operators, strict=True))
        assert differences == 1


def test_handles_nested_unary_expressions_and_generates_valid_python() -> None:
    original = _chunk("def check(value):\n    return not -value\n")

    mutants = UnaryMutation().mutate(original)

    assert len(mutants) == 6
    assert len({mutant.chunk_id for mutant in mutants}) == 6
    for mutant in mutants:
        ast.parse(mutant.code)
        compile(mutant.code, "<unary-mutant>", "exec")
        assert mutant.parent is original


def test_supports_async_functions() -> None:
    original = _chunk("async def negate(value):\n    return -value\n")

    mutants = UnaryMutation().mutate(original)

    assert len(mutants) == 3
    assert all(isinstance(ast.parse(mutant.code).body[0], ast.AsyncFunctionDef) for mutant in mutants)


def test_returns_no_mutants_without_unary_expressions() -> None:
    original = _chunk("def identity(value):\n    return value\n")

    assert UnaryMutation().mutate(original) == []


def test_integrates_with_module_generation_and_avoids_duplicate_higher_order_states() -> None:
    module = Module("example", "example.py")
    original = CodeChunk("def negate(value):\n    return -value\n", module.module_id, "negate", "function", 1, 2)
    module.code_chunks.append(original)

    mutants = generate_mutants(module, [UnaryMutation], max_degree=2)

    assert len(mutants) == 3
    assert all(mutant.mutation_degree == 1 for mutant in mutants)
    assert all(mutant.module is module for mutant in mutants)
    assert module.code_chunks == [original, *mutants]
    assert original.derived_chunks == mutants
