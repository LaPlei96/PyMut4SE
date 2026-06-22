import ast
import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, cast

from pymut4se.model import CodeChunk, Module
from pymut4se.mutation import generate_mutants
from pymut4se.mutation.generic import ReturnPassMutation


def _chunk(source: str, *, start_line: int = 1) -> CodeChunk:
    return CodeChunk(
        source,
        "module",
        "example",
        "function",
        start_line,
        start_line + len(source.splitlines()) - 1,
    )


def test_replaces_the_function_body_and_returns_none() -> None:
    original = _chunk("def execute():\n    raise RuntimeError('must not run')\n", start_line=10)

    mutants = ReturnPassMutation().mutate(original)

    assert len(mutants) == 1
    namespace: dict[str, object] = {}
    exec(mutants[0].code, namespace)
    function = namespace["execute"]
    assert callable(function)
    assert cast(Callable[[], object], function)() is None
    assert mutants[0].mutation_type == "return_pass"
    assert mutants[0].mutation_operator == "replace_body_with_pass"
    assert mutants[0].line_changed == 11
    assert mutants[0].column_changed == 5


def test_preserves_the_function_docstring() -> None:
    original = _chunk('def execute():\n    """Execute the operation."""\n    return 42\n')

    mutant = ReturnPassMutation().mutate(original)[0]
    function_node = ast.parse(mutant.code).body[0]
    assert isinstance(function_node, ast.FunctionDef)
    assert isinstance(function_node.body[0], ast.Expr)
    assert isinstance(function_node.body[1], ast.Pass)
    namespace: dict[str, object] = {}
    exec(mutant.code, namespace)
    function = namespace["execute"]
    assert getattr(function, "__doc__") == "Execute the operation."


def test_supports_async_functions() -> None:
    original = _chunk("async def execute():\n    return 42\n")

    mutant = ReturnPassMutation().mutate(original)[0]
    namespace: dict[str, object] = {}
    exec(mutant.code, namespace)
    function = namespace["execute"]
    assert callable(function)
    coroutine = cast(Callable[[], Coroutine[Any, Any, object]], function)()
    assert asyncio.run(coroutine) is None
    assert isinstance(ast.parse(mutant.code).body[0], ast.AsyncFunctionDef)


def test_only_replaces_the_outer_function_represented_by_the_chunk() -> None:
    original = _chunk("def outer():\n    def inner():\n        return 1\n    return inner()\n")

    mutant = ReturnPassMutation().mutate(original)[0]
    outer = ast.parse(mutant.code).body[0]
    assert isinstance(outer, ast.FunctionDef)
    assert len(outer.body) == 1
    assert isinstance(outer.body[0], ast.Pass)
    assert not any(isinstance(node, ast.FunctionDef) and node.name == "inner" for node in ast.walk(outer))


def test_skips_functions_that_already_only_pass_and_non_function_chunks() -> None:
    pass_function = _chunk("def execute():\n    pass\n")
    statement = CodeChunk("value = 1", "module", "assignment", "statement", 1, 1)

    assert ReturnPassMutation().mutate(pass_function) == []
    assert ReturnPassMutation().mutate(statement) == []


def test_integrates_with_module_generation_and_orm_relationships() -> None:
    module = Module("example", "example.py")
    original = CodeChunk("def execute():\n    return 42\n", module.module_id, "execute", "function", 1, 2)
    module.code_chunks.append(original)

    mutants = generate_mutants(module, [ReturnPassMutation], max_degree=1)

    assert len(mutants) == 1
    assert mutants[0].module is module
    assert mutants[0].parent is original
    assert module.code_chunks == [original, *mutants]
