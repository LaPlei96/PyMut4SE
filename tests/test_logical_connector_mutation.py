import ast

from pymut4se.model import CodeChunk, Module
from pymut4se.mutation import generate_mutants
from pymut4se.mutation.generic import LogicalConnectorMutation


def _chunk(source: str, *, start_line: int = 1) -> CodeChunk:
    return CodeChunk(
        source,
        "module",
        "example",
        "function",
        start_line,
        start_line + len(source.splitlines()) - 1,
    )


def _connector_names(source: str) -> list[str]:
    return [type(node.op).__name__ for node in ast.walk(ast.parse(source)) if isinstance(node, ast.BoolOp)]


def test_replaces_and_with_or_and_or_with_and() -> None:
    original = _chunk(
        "def allowed(active, admin, owner, trusted):\n    return active and trusted, admin or owner\n",
        start_line=10,
    )

    mutants = LogicalConnectorMutation().mutate(original)

    assert len(mutants) == 2
    assert {_connector_names(mutant.code)[0] for mutant in mutants} == {"And", "Or"}
    assert {mutant.mutation_operator for mutant in mutants} == {"And", "Or"}
    assert {mutant.mutation_type for mutant in mutants} == {"logical_connector"}
    assert {mutant.line_changed for mutant in mutants} == {11}
    assert {mutant.column_changed for mutant in mutants} == {12, 32}


def test_changes_a_complete_chained_boolean_expression() -> None:
    original = _chunk("def all_ready(first, second, third):\n    return first and second and third\n")

    mutants = LogicalConnectorMutation().mutate(original)

    assert len(mutants) == 1
    assert _connector_names(mutants[0].code) == ["Or"]
    assert "first or second or third" in mutants[0].code


def test_mutates_one_nested_expression_even_when_locations_overlap() -> None:
    original = _chunk("def choose(left, middle, right):\n    return left and middle or right\n")
    original_connectors = _connector_names(original.code)

    mutants = LogicalConnectorMutation().mutate(original)

    assert len(mutants) == 2
    for mutant in mutants:
        connectors = _connector_names(mutant.code)
        assert sum(before != after for before, after in zip(original_connectors, connectors, strict=True)) == 1
        compile(mutant.code, "<logical-connector-mutant>", "exec")


def test_supports_async_functions_and_ignores_code_without_connectors() -> None:
    async_chunk = _chunk("async def ready(first, second):\n    return first and second\n")
    plain_chunk = _chunk("def identity(value):\n    return value\n")

    mutants = LogicalConnectorMutation().mutate(async_chunk)

    assert len(mutants) == 1
    assert isinstance(ast.parse(mutants[0].code).body[0], ast.AsyncFunctionDef)
    assert LogicalConnectorMutation().mutate(plain_chunk) == []


def test_integrates_with_generation_and_avoids_inverse_higher_order_duplicates() -> None:
    module = Module("example", "example.py")
    original = CodeChunk(
        "def ready(first, second):\n    return first and second\n",
        module.module_id,
        "ready",
        "function",
        1,
        2,
    )
    module.code_chunks.append(original)

    mutants = generate_mutants(module, [LogicalConnectorMutation], max_degree=2)

    assert len(mutants) == 1
    assert mutants[0].mutation_degree == 1
    assert mutants[0].parent is original
    assert mutants[0].original is original
    assert module.code_chunks == [original, *mutants]
    assert original.derived_chunks == mutants
