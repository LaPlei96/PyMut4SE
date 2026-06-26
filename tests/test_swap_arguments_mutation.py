import ast

from pymut4se.model import CodeChunk, Module
from pymut4se.mutation import generate_mutants
from pymut4se.mutation.generic import SwapArgumentsMutation


def _chunk(source: str, *, start_line: int = 1) -> CodeChunk:
    return CodeChunk(
        source,
        "module",
        "example",
        "function",
        start_line,
        start_line + len(source.splitlines()) - 1,
    )


def _call_arguments(source: str, function_name: str) -> list[list[str]]:
    return [
        [ast.unparse(argument) for argument in node.args]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == function_name
    ]


def test_swaps_two_positional_arguments() -> None:
    original = _chunk("def load(start, end):\n    return read(start, end)\n", start_line=10)

    mutants = SwapArgumentsMutation().mutate(original)

    assert len(mutants) == 1
    assert _call_arguments(mutants[0].code, "read") == [["end", "start"]]
    assert mutants[0].mutation_type == "swap_arguments"
    assert mutants[0].mutation_operator == "swap:0:1"
    assert mutants[0].line_changed == 11
    assert mutants[0].column_changed == 12
    assert mutants[0].parent is original


def test_creates_every_pairwise_swap_for_three_arguments() -> None:
    original = _chunk("def combine(first, second, third):\n    return merge(first, second, third)\n")

    mutants = SwapArgumentsMutation().mutate(original)

    assert len(mutants) == 3
    assert {tuple(_call_arguments(mutant.code, "merge")[0]) for mutant in mutants} == {
        ("second", "first", "third"),
        ("third", "second", "first"),
        ("first", "third", "second"),
    }
    assert {mutant.mutation_operator for mutant in mutants} == {
        "swap:0:1",
        "swap:0:2",
        "swap:1:2",
    }


def test_mutates_each_call_site_independently() -> None:
    original = _chunk(
        "def copy(source_start, source_end, target_start, target_end):\n"
        "    first = read(source_start, source_end)\n"
        "    second = read(target_start, target_end)\n"
        "    return first, second\n"
    )
    original_calls = _call_arguments(original.code, "read")

    mutants = SwapArgumentsMutation().mutate(original)

    assert len(mutants) == 2
    for mutant in mutants:
        mutated_calls = _call_arguments(mutant.code, "read")
        assert sum(before != after for before, after in zip(original_calls, mutated_calls, strict=True)) == 1
        compile(mutant.code, "<swap-arguments-mutant>", "exec")


def test_supports_attribute_calls_and_async_functions() -> None:
    original = _chunk("async def transfer(client, start, end):\n    return await client.read(start, end)\n")

    mutants = SwapArgumentsMutation().mutate(original)

    assert len(mutants) == 1
    call = next(node for node in ast.walk(ast.parse(mutants[0].code)) if isinstance(node, ast.Call))
    assert [ast.unparse(argument) for argument in call.args] == ["end", "start"]
    assert isinstance(ast.parse(mutants[0].code).body[0], ast.AsyncFunctionDef)


def test_ignores_keyword_only_and_starred_argument_calls() -> None:
    original = _chunk(
        "def load(start, end, bounds):\n"
        "    first = read(start=start, end=end)\n"
        "    second = read(*bounds, end)\n"
        "    return first, second\n"
    )

    assert SwapArgumentsMutation().mutate(original) == []


def test_integrates_with_generation_and_avoids_inverse_higher_order_duplicates() -> None:
    module = Module("example", "example.py")
    original = CodeChunk(
        "def load(start, end):\n    return read(start, end)\n",
        module.module_id,
        "load",
        "function",
        1,
        2,
    )
    module.code_chunks.append(original)

    mutants = generate_mutants(module, [SwapArgumentsMutation], max_degree=2)

    assert len(mutants) == 1
    assert mutants[0].mutation_degree == 1
    assert mutants[0].original is original
    assert module.code_chunks == [original, *mutants]
    assert original.derived_chunks == mutants
