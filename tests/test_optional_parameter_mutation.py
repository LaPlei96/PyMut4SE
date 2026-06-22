import ast
from collections.abc import Callable
from typing import cast

from pymut4se.model import CodeChunk, Module
from pymut4se.mutation import generate_mutants
from pymut4se.mutation.generic import OptionalParamCalleeMutation, OptionalParamCallerMutation


def _module_with_chunks(callee_source: str, caller_source: str, *, caller_start: int = 10):
    module = Module("example", "example.py")
    callee = CodeChunk(
        callee_source,
        module.module_id,
        "callee",
        "function",
        1,
        len(callee_source.splitlines()),
    )
    caller = CodeChunk(
        caller_source,
        module.module_id,
        "caller",
        "function",
        caller_start,
        caller_start + len(caller_source.splitlines()) - 1,
    )
    module.code_chunks.extend([callee, caller])
    return module, callee, caller


def _assert_valid(mutants: list[CodeChunk], expected_type: str = "optional_param_caller") -> None:
    for mutant in mutants:
        ast.parse(mutant.code)
        compile(mutant.code, "<optional-param-mutant>", "exec")
        assert mutant.mutation_type == expected_type
        assert mutant.parent is not None


def test_adds_omitted_positional_and_keyword_only_defaults_from_sibling_signature() -> None:
    _, _, caller = _module_with_chunks(
        "def callee(value, limit: int = 10, *, enabled: bool = False):\n    return value\n",
        "def caller():\n    return callee(1)\n",
    )

    mutants = OptionalParamCallerMutation().mutate(caller)

    assert len(mutants) == 2
    assert {mutant.mutation_operator for mutant in mutants} == {"add:limit", "add:enabled"}
    assert any("limit=0" in mutant.code for mutant in mutants)
    assert any("enabled=True" in mutant.code for mutant in mutants)
    assert {mutant.line_changed for mutant in mutants} == {11}
    _assert_valid(mutants)


def test_removes_an_explicit_optional_keyword() -> None:
    _, callee, caller = _module_with_chunks(
        "def callee(value, limit: int = 10):\n    return value + limit\n",
        "def caller():\n    return callee(5, limit=3)\n",
    )

    mutants = OptionalParamCallerMutation().mutate(caller)

    assert len(mutants) == 1
    assert mutants[0].mutation_operator == "remove:limit"
    assert "limit=" not in mutants[0].code
    namespace: dict[str, object] = {}
    exec(callee.code, namespace)
    exec(mutants[0].code, namespace)
    caller_function = namespace["caller"]
    assert callable(caller_function)
    assert cast(Callable[[], int], caller_function)() == 15


def test_does_not_add_parameters_already_supplied_positionally() -> None:
    _, _, caller = _module_with_chunks(
        "def callee(value, limit: int = 10):\n    return value + limit\n",
        "def caller():\n    return callee(5, 3)\n",
    )

    assert OptionalParamCallerMutation().mutate(caller) == []


def test_skips_additions_when_starred_arguments_or_keyword_expansions_are_present() -> None:
    _, _, positional_caller = _module_with_chunks(
        "def callee(value, limit: int = 10):\n    return value + limit\n",
        "def caller(arguments):\n    return callee(*arguments)\n",
    )
    _, _, keyword_caller = _module_with_chunks(
        "def callee(value, limit: int = 10):\n    return value + limit\n",
        "def caller(options):\n    return callee(1, **options)\n",
    )

    assert OptionalParamCallerMutation().mutate(positional_caller) == []
    assert OptionalParamCallerMutation().mutate(keyword_caller) == []


def test_uses_typed_local_values_before_configured_fallbacks() -> None:
    _, _, caller = _module_with_chunks(
        "def callee(value, limit: int = 10):\n    return value + limit\n",
        "def caller():\n    selected: int = 7\n    return callee(1)\n",
    )

    mutants = OptionalParamCallerMutation({"int": 99}).mutate(caller)

    assert len(mutants) == 1
    assert "limit=selected" in mutants[0].code


def test_preserves_configured_container_fallback_contents() -> None:
    _, _, caller = _module_with_chunks(
        "def callee(*, items: list[int] = []):\n    return items\n",
        "def caller():\n    return callee()\n",
    )

    mutants = OptionalParamCallerMutation({"list": [1, 2]}).mutate(caller)

    assert len(mutants) == 1
    assert "items=[1, 2]" in mutants[0].code


def test_changes_a_fallback_that_equals_the_declared_default() -> None:
    _, _, caller = _module_with_chunks(
        "def callee(limit: int = 0):\n    return limit\n",
        "def caller():\n    return callee()\n",
    )

    mutants = OptionalParamCallerMutation().mutate(caller)

    assert len(mutants) == 1
    assert "limit=1" in mutants[0].code


def test_resolves_optional_generic_annotations_to_their_value_type() -> None:
    _, _, caller = _module_with_chunks(
        "def callee(limit: Optional[int] = None):\n    return limit\n",
        "def caller():\n    return callee()\n",
    )

    mutants = OptionalParamCallerMutation().mutate(caller)

    assert len(mutants) == 1
    assert "limit=0" in mutants[0].code


def test_supports_async_function_signatures_and_calls() -> None:
    _, _, caller = _module_with_chunks(
        "async def callee(value, enabled: bool = False):\n    return value\n",
        "async def caller():\n    return await callee(1)\n",
    )

    mutants = OptionalParamCallerMutation().mutate(caller)

    assert len(mutants) == 1
    assert "enabled=True" in mutants[0].code
    assert isinstance(ast.parse(mutants[0].code).body[0], ast.AsyncFunctionDef)


def test_integrates_with_module_generation_and_orm_relationships() -> None:
    module, _, caller = _module_with_chunks(
        "def callee(value, limit: int = 10):\n    return value + limit\n",
        "def caller():\n    return callee(5)\n",
    )

    mutants = generate_mutants(module, [OptionalParamCallerMutation], max_degree=1)

    assert len(mutants) == 1
    assert mutants[0].parent is caller
    assert mutants[0].module is module
    assert module.code_chunks[-1] is mutants[0]


def test_callee_variant_replaces_positional_and_keyword_only_defaults() -> None:
    source = "def callee(value: int = 10, /, *, enabled: bool = False):\n    return value if enabled else -value\n"
    callee = CodeChunk(source, "module", "callee", "function", 20, 21)

    mutants = OptionalParamCalleeMutation().mutate(callee)

    assert len(mutants) == 2
    assert {mutant.mutation_operator for mutant in mutants} == {
        "replace_default:value",
        "replace_default:enabled",
    }
    assert {mutant.mutation_type for mutant in mutants} == {"optional_param_callee"}
    assert {mutant.line_changed for mutant in mutants} == {20}
    value_mutant = next(mutant for mutant in mutants if mutant.mutation_operator == "replace_default:value")
    enabled_mutant = next(mutant for mutant in mutants if mutant.mutation_operator == "replace_default:enabled")
    assert "value: int=0" in value_mutant.code
    assert "enabled: bool=True" in enabled_mutant.code
    _assert_valid(mutants, "optional_param_callee")


def test_callee_variant_changes_behavior_when_callers_omit_the_parameter() -> None:
    callee = CodeChunk(
        "def callee(limit: int = 10):\n    return limit\n",
        "module",
        "callee",
        "function",
        1,
        2,
    )

    mutant = OptionalParamCalleeMutation().mutate(callee)[0]
    namespace: dict[str, object] = {}
    exec(mutant.code, namespace)
    callee_function = namespace["callee"]
    assert callable(callee_function)
    assert cast(Callable[[], int], callee_function)() == 0


def test_callee_variant_leaves_callers_and_nested_defaults_unchanged() -> None:
    source = (
        "def callee(value: int = 10):\n    def nested(flag: bool = False):\n        return flag\n    return value\n"
    )
    callee = CodeChunk(source, "module", "callee", "function", 1, 4)

    mutants = OptionalParamCalleeMutation().mutate(callee)

    assert len(mutants) == 1
    tree = ast.parse(mutants[0].code)
    outer = tree.body[0]
    assert isinstance(outer, ast.FunctionDef)
    nested = next(statement for statement in outer.body if isinstance(statement, ast.FunctionDef))
    nested_default = nested.args.defaults[0]
    assert isinstance(nested_default, ast.Constant)
    assert nested_default.value is False


def test_callee_variant_supports_async_functions_and_custom_fallbacks() -> None:
    callee = CodeChunk(
        "async def callee(items: list[str] = []):\n    return items\n",
        "module",
        "callee",
        "function",
        1,
        2,
    )

    mutants = OptionalParamCalleeMutation({"list": ["changed"]}).mutate(callee)

    assert len(mutants) == 1
    assert "items: list[str]=['changed']" in mutants[0].code
    assert isinstance(ast.parse(mutants[0].code).body[0], ast.AsyncFunctionDef)


def test_callee_variant_integrates_with_module_generation_without_changing_caller_source() -> None:
    module, callee, caller = _module_with_chunks(
        "def callee(limit: int = 10):\n    return limit\n",
        "def caller():\n    return callee()\n",
    )
    caller_source = caller.code

    mutants = generate_mutants(module, [OptionalParamCalleeMutation], max_degree=1)

    assert len(mutants) == 1
    assert mutants[0].parent is callee
    assert mutants[0].module is module
    assert caller.code == caller_source
