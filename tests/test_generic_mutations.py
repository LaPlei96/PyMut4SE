import ast

import pytest

from pymut4se.model import CodeChunk
from pymut4se.mutation import generate_mutants
from pymut4se.mutation.generic import (
    ArithmeticMutation,
    IfNotNullMutation,
    RelationalMutation,
    TypeCastMutation,
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


def _assert_valid_mutants(mutants: list[CodeChunk], expected_type: str) -> None:
    assert mutants
    assert len({mutant.chunk_id for mutant in mutants}) == len(mutants)
    for mutant in mutants:
        ast.parse(mutant.code)
        compile(mutant.code, "<mutant>", "exec")
        assert mutant.mutation_type == expected_type
        assert mutant.mutation_degree == 1
        assert mutant.parent is not None


def test_arithmetic_mutation_replaces_one_binary_operator_per_mutant() -> None:
    original = _chunk("def calculate(left, right):\n    return left + right\n", start_line=10)

    mutants = ArithmeticMutation().mutate(original)

    assert len(mutants) == 11
    assert {mutant.mutation_operator for mutant in mutants} == {
        "Sub",
        "Mult",
        "MatMult",
        "Div",
        "Mod",
        "Pow",
        "LShift",
        "RShift",
        "BitOr",
        "BitXor",
        "FloorDiv",
    }
    assert {mutant.line_changed for mutant in mutants} == {11}
    _assert_valid_mutants(mutants, "arithmetic")


def test_relational_mutation_handles_each_operator_in_a_chained_comparison() -> None:
    original = _chunk("def within(lower, value, upper):\n    return lower < value <= upper\n")

    mutants = RelationalMutation().mutate(original)

    assert len(mutants) == 18
    assert {mutant.mutation_operator for mutant in mutants} == {
        "Eq",
        "NotEq",
        "Lt",
        "LtE",
        "Gt",
        "GtE",
        "Is",
        "IsNot",
        "In",
        "NotIn",
    }
    _assert_valid_mutants(mutants, "comparison")


def test_type_cast_mutation_covers_parameters_without_mutating_nested_functions() -> None:
    original = _chunk(
        "def convert(self, value, /, count=1, *, scale=1):\n"
        '    """Convert values."""\n'
        "    def normalize(item):\n"
        "        return item\n"
        "    return normalize(value) * count * scale\n"
    )

    mutants = TypeCastMutation().mutate(original)

    assert len(mutants) == 9
    selected = next(mutant for mutant in mutants if mutant.mutation_operator == "value:int")
    function = ast.parse(selected.code).body[0]
    assert isinstance(function, ast.FunctionDef)
    assert isinstance(function.body[0], ast.Expr)
    assert isinstance(function.body[1], ast.Assign)
    nested = next(statement for statement in function.body if isinstance(statement, ast.FunctionDef))
    assert isinstance(nested.body[0], ast.Return)
    assert selected.line_changed == 3
    _assert_valid_mutants(mutants, "cast_type")


def test_if_not_null_preserves_docstrings_and_only_guards_the_outer_function() -> None:
    original = _chunk(
        "def execute(self, value):\n"
        '    """Execute with a value."""\n'
        "    def normalize(item):\n"
        "        return item\n"
        "    return normalize(value)\n"
    )

    mutants = IfNotNullMutation().mutate(original)

    assert len(mutants) == 1
    function = ast.parse(mutants[0].code).body[0]
    assert isinstance(function, ast.FunctionDef)
    assert isinstance(function.body[0], ast.Expr)
    guard = function.body[1]
    assert isinstance(guard, ast.If)
    nested = next(statement for statement in guard.body if isinstance(statement, ast.FunctionDef))
    assert isinstance(nested.body[0], ast.Return)
    assert mutants[0].mutation_operator == "value"
    assert mutants[0].line_changed == 3
    _assert_valid_mutants(mutants, "if_not_null")


@pytest.mark.parametrize("operator", [TypeCastMutation(), IfNotNullMutation()])
def test_parameter_mutations_support_async_functions(operator: TypeCastMutation | IfNotNullMutation) -> None:
    original = _chunk("async def execute(value):\n    return value\n")

    mutants = operator.mutate(original)

    assert mutants
    assert all(isinstance(ast.parse(mutant.code).body[0], ast.AsyncFunctionDef) for mutant in mutants)


@pytest.mark.parametrize("operator", [TypeCastMutation(), IfNotNullMutation()])
def test_parameter_mutations_ignore_chunks_without_functions(operator: TypeCastMutation | IfNotNullMutation) -> None:
    original = CodeChunk("value = 1", "module", "assignment", "statement", 1, 1)

    assert operator.mutate(original) == []


def test_completed_operators_integrate_with_degree_limited_generation() -> None:
    original = _chunk("def compare(left, right):\n    return left + right < right\n")

    mutants = generate_mutants(
        original,
        [ArithmeticMutation, RelationalMutation, TypeCastMutation, IfNotNullMutation],
        max_degree=1,
    )

    assert len(mutants) == 28
    assert {mutant.mutation_type for mutant in mutants} == {
        "arithmetic",
        "comparison",
        "cast_type",
        "if_not_null",
    }
