import ast

from pymut4se.model import CodeChunk, Module
from pymut4se.mutation import generate_mutants
from pymut4se.mutation.generic import ControlReplacementMutation


def _chunk(source: str, *, start_line: int = 1) -> CodeChunk:
    return CodeChunk(
        source,
        "module",
        "example",
        "function",
        start_line,
        start_line + len(source.splitlines()) - 1,
    )


def _control_names(source: str) -> list[str]:
    return [type(node).__name__ for node in ast.walk(ast.parse(source)) if isinstance(node, (ast.Break, ast.Continue))]


def test_replaces_break_and_continue_independently() -> None:
    original = _chunk(
        "def process(values):\n"
        "    for value in values:\n"
        "        if value is None:\n"
        "            continue\n"
        "        if value < 0:\n"
        "            break\n",
        start_line=10,
    )
    original_controls = _control_names(original.code)

    mutants = ControlReplacementMutation().mutate(original)

    assert len(mutants) == 2
    assert {mutant.mutation_operator for mutant in mutants} == {
        "replace_with_break",
        "replace_with_continue",
    }
    assert {mutant.mutation_type for mutant in mutants} == {"control_replacement"}
    assert {mutant.line_changed for mutant in mutants} == {13, 15}
    assert {mutant.column_changed for mutant in mutants} == {13}
    for mutant in mutants:
        mutated_controls = _control_names(mutant.code)
        assert sum(before != after for before, after in zip(original_controls, mutated_controls, strict=True)) == 1
        compile(mutant.code, "<control-replacement-mutant>", "exec")


def test_handles_nested_loops() -> None:
    original = _chunk(
        "def search(rows):\n"
        "    for row in rows:\n"
        "        for value in row:\n"
        "            if value is None:\n"
        "                continue\n"
        "            break\n"
    )

    mutants = ControlReplacementMutation().mutate(original)

    assert len(mutants) == 2
    assert len({mutant.chunk_id for mutant in mutants}) == 2
    assert all(mutant.parent is original for mutant in mutants)


def test_supports_async_functions_and_ignores_functions_without_loop_control() -> None:
    async_chunk = _chunk(
        "async def consume(stream):\n    async for item in stream:\n        if item is None:\n            continue\n"
    )
    plain_chunk = _chunk("def identity(value):\n    return value\n")

    mutants = ControlReplacementMutation().mutate(async_chunk)

    assert len(mutants) == 1
    assert _control_names(mutants[0].code) == ["Break"]
    assert isinstance(ast.parse(mutants[0].code).body[0], ast.AsyncFunctionDef)
    assert ControlReplacementMutation().mutate(plain_chunk) == []


def test_integrates_with_generation_and_avoids_inverse_higher_order_duplicates() -> None:
    module = Module("example", "example.py")
    original = CodeChunk(
        "def first(values):\n    for value in values:\n        break\n",
        module.module_id,
        "first",
        "function",
        1,
        3,
    )
    module.code_chunks.append(original)

    mutants = generate_mutants(module, [ControlReplacementMutation], max_degree=2)

    assert len(mutants) == 1
    assert mutants[0].mutation_degree == 1
    assert mutants[0].parent is original
    assert mutants[0].original is original
    assert module.code_chunks == [original, *mutants]
    assert original.derived_chunks == mutants
