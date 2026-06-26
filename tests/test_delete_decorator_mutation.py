import ast
from pathlib import Path

from pymut4se.exploration import explore_path
from pymut4se.model import CodeChunk, Module
from pymut4se.mutation import build_mutant, generate_mutants
from pymut4se.mutation.generic import DeleteDecoratorMutation


def _chunk(source: str, *, start_line: int = 1) -> CodeChunk:
    return CodeChunk(
        source,
        "module",
        "example",
        "function",
        start_line,
        start_line + len(source.splitlines()) - 1,
    )


def _decorator_names(source: str) -> list[str]:
    function = ast.parse(source).body[0]
    assert isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
    return [ast.unparse(decorator) for decorator in function.decorator_list]


def test_deletes_each_decorator_independently() -> None:
    original = _chunk(
        "@staticmethod\n@cache(timeout=5)\n@registry.handler\ndef load(value):\n    return value\n",
        start_line=10,
    )

    mutants = DeleteDecoratorMutation().mutate(original)

    assert len(mutants) == 3
    assert {mutant.mutation_operator for mutant in mutants} == {
        "delete:staticmethod",
        "delete:cache(timeout=5)",
        "delete:registry.handler",
    }
    assert {mutant.mutation_type for mutant in mutants} == {"delete_decorator"}
    assert {mutant.line_changed for mutant in mutants} == {10, 11, 12}
    assert {mutant.column_changed for mutant in mutants} == {1}
    assert all(len(_decorator_names(mutant.code)) == 2 for mutant in mutants)
    assert all(mutant.parent is original for mutant in mutants)


def test_only_deletes_decorators_from_the_function_represented_by_the_chunk() -> None:
    original = _chunk(
        "@outer_decorator\n"
        "def outer():\n"
        "    @inner_decorator\n"
        "    def inner():\n"
        "        return True\n"
        "    return inner()\n"
    )

    mutants = DeleteDecoratorMutation().mutate(original)

    assert len(mutants) == 1
    assert _decorator_names(mutants[0].code) == []
    nested = next(node for node in ast.walk(ast.parse(mutants[0].code)) if isinstance(node, ast.FunctionDef))
    assert nested.name == "outer"
    inner = next(node for node in ast.walk(nested) if isinstance(node, ast.FunctionDef) and node.name == "inner")
    assert [ast.unparse(decorator) for decorator in inner.decorator_list] == ["inner_decorator"]


def test_supports_async_functions_and_ignores_undecorated_functions() -> None:
    decorated = _chunk("@trace\nasync def execute():\n    return None\n")
    undecorated = _chunk("def execute():\n    return None\n")

    mutants = DeleteDecoratorMutation().mutate(decorated)

    assert len(mutants) == 1
    assert isinstance(ast.parse(mutants[0].code).body[0], ast.AsyncFunctionDef)
    assert DeleteDecoratorMutation().mutate(undecorated) == []


def test_exploration_includes_multiple_decorators_and_builds_each_complete_mutant(
    temp_path: Path,
) -> None:
    source_path = temp_path / "decorated.py"
    source_path.write_text(
        "def trace(function):\n"
        "    return function\n\n"
        "def configured(**options):\n"
        "    return trace\n\n"
        "@trace\n"
        '@configured(mode="fast")\n'
        "def execute():\n"
        "    return True\n",
        encoding="utf-8",
    )

    result = explore_path(source_path)
    execute = next(chunk for chunk in result.code_chunks if chunk.function_name == "execute")
    mutants = DeleteDecoratorMutation().mutate(execute)

    assert execute.start_line == 7
    assert execute.end_line == 10
    assert execute.code == ('@trace\n@configured(mode="fast")\ndef execute():\n    return True\n')
    assert _decorator_names(execute.code) == ["trace", "configured(mode='fast')"]
    assert len(mutants) == 2
    assert {mutant.mutation_operator for mutant in mutants} == {
        "delete:trace",
        "delete:configured(mode='fast')",
    }

    built_modules = [build_mutant(mutant) for mutant in mutants]
    remaining_decorators = []
    for module_source in built_modules:
        parsed_module = ast.parse(module_source)
        built_execute = next(
            node for node in parsed_module.body if isinstance(node, ast.FunctionDef) and node.name == "execute"
        )
        remaining_decorators.append([ast.unparse(decorator) for decorator in built_execute.decorator_list])

    assert remaining_decorators == [
        ["configured(mode='fast')"],
        ["trace"],
    ]


def test_integrates_with_generation_and_deduplicates_decorator_deletion_order() -> None:
    module = Module("example", "example.py")
    original = CodeChunk(
        "@first\n@second\ndef execute():\n    return True\n",
        module.module_id,
        "execute",
        "function",
        1,
        4,
    )
    module.code_chunks.append(original)

    mutants = generate_mutants(module, [DeleteDecoratorMutation], max_degree=2)

    assert len(mutants) == 3
    assert sum(mutant.mutation_degree == 1 for mutant in mutants) == 2
    assert sum(mutant.mutation_degree == 2 for mutant in mutants) == 1
    assert _decorator_names(mutants[-1].code) == []
    assert all(mutant.original is original for mutant in mutants)
