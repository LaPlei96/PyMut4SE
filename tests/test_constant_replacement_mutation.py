import ast
from collections.abc import Callable
from typing import cast

from pymut4se.model import CodeChunk, Module
from pymut4se.mutation import generate_mutants
from pymut4se.mutation.generic import BooleanReplacementMutation, ConstantReplacementMutation


def _chunk(source: str, *, start_line: int = 1) -> CodeChunk:
    return CodeChunk(
        source,
        "module",
        "example",
        "function",
        start_line,
        start_line + len(source.splitlines()) - 1,
    )


def _execute(mutant: CodeChunk, function_name: str = "constant") -> object:
    namespace: dict[str, object] = {}
    exec(mutant.code, namespace)
    function = namespace[function_name]
    assert callable(function)
    return cast(Callable[[], object], function)()


def test_creates_four_replacements_for_an_integer_constant() -> None:
    original = _chunk("def constant():\n    return 5\n", start_line=10)

    mutants = ConstantReplacementMutation().mutate(original)

    assert len(mutants) == 4
    assert {mutant.mutation_operator for mutant in mutants} == {
        "add_one",
        "subtract_one",
        "absolute",
        "negate",
    }
    results = {mutant.mutation_operator: _execute(mutant) for mutant in mutants}
    assert results == {
        "add_one": 6,
        "subtract_one": 4,
        "absolute": 5,
        "negate": -5,
    }
    assert {mutant.mutation_type for mutant in mutants} == {"constant_replacement"}
    assert {mutant.line_changed for mutant in mutants} == {11}
    assert {mutant.column_changed for mutant in mutants} == {12}


def test_treats_a_negative_literal_as_one_signed_constant() -> None:
    original = _chunk("def constant():\n    return -5\n")

    mutants = ConstantReplacementMutation().mutate(original)

    assert len(mutants) == 4
    results = {mutant.mutation_operator: _execute(mutant) for mutant in mutants}
    assert results == {
        "add_one": -4,
        "subtract_one": -6,
        "absolute": 5,
        "negate": 5,
    }


def test_mutates_each_constant_location_independently() -> None:
    original = _chunk("def total():\n    return 2 + 3\n")

    mutants = ConstantReplacementMutation().mutate(original)

    assert len(mutants) == 8
    assert len({mutant.chunk_id for mutant in mutants}) == 8
    for mutant in mutants:
        ast.parse(mutant.code)
        compile(mutant.code, "<constant-mutant>", "exec")
        assert mutant.parent is original


def test_ignores_non_numeric_constants_including_booleans() -> None:
    original = _chunk("def values():\n    return True, False, None, 'text', b'bytes', ...\n")

    assert ConstantReplacementMutation().mutate(original) == []


def test_supports_float_complex_default_and_async_constants() -> None:
    float_chunk = _chunk("def constant(value=1.5):\n    return value\n")
    complex_chunk = _chunk("async def constant():\n    return 2j\n")

    float_mutants = ConstantReplacementMutation().mutate(float_chunk)
    complex_mutants = ConstantReplacementMutation().mutate(complex_chunk)

    assert len(float_mutants) == 4
    assert len(complex_mutants) == 4
    assert all(isinstance(ast.parse(mutant.code).body[0], ast.AsyncFunctionDef) for mutant in complex_mutants)


def test_integrates_with_module_generation_and_orm_relationships() -> None:
    module = Module("example", "example.py")
    original = CodeChunk("def constant():\n    return 5\n", module.module_id, "constant", "function", 1, 2)
    module.code_chunks.append(original)

    mutants = generate_mutants(module, [ConstantReplacementMutation], max_degree=1)

    assert len(mutants) == 4
    assert all(mutant.module is module for mutant in mutants)
    assert all(mutant.parent is original for mutant in mutants)
    assert module.code_chunks == [original, *mutants]


def test_boolean_replacement_inverts_true_and_false_independently() -> None:
    original = _chunk("def flags():\n    return True, False\n")

    mutants = BooleanReplacementMutation().mutate(original)

    assert len(mutants) == 2
    results = [_execute(mutant, "flags") for mutant in mutants]
    assert set(results) == {(False, False), (True, True)}
    assert {mutant.mutation_type for mutant in mutants} == {"boolean_replacement"}
    assert {mutant.mutation_operator for mutant in mutants} == {"invert_boolean"}


def test_boolean_replacement_ignores_numeric_and_other_constants() -> None:
    original = _chunk("def values():\n    return 1, 0, 'True', None\n")

    assert BooleanReplacementMutation().mutate(original) == []


def test_boolean_replacement_supports_defaults_and_async_functions() -> None:
    original = _chunk("async def enabled(flag=True):\n    return flag\n")

    mutants = BooleanReplacementMutation().mutate(original)

    assert len(mutants) == 1
    assert "flag=False" in mutants[0].code
    assert isinstance(ast.parse(mutants[0].code).body[0], ast.AsyncFunctionDef)


def test_boolean_replacement_avoids_inverse_higher_order_duplicates() -> None:
    module = Module("example", "example.py")
    original = CodeChunk("def enabled():\n    return True\n", module.module_id, "enabled", "function", 1, 2)
    module.code_chunks.append(original)

    mutants = generate_mutants(module, [BooleanReplacementMutation], max_degree=2)

    assert len(mutants) == 1
    assert mutants[0].mutation_degree == 1
    assert mutants[0].module is module
    assert module.code_chunks == [original, *mutants]
