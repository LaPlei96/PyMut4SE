import re
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from pymut4se.api import MutationWorkspace, available_operators, discover
from pymut4se.api.operators import resolve_operators
from pymut4se.execution import PythonExecutionEnvironment
from pymut4se.model import Base, CodeChunk, FunctionInput, TestExecutionOutput as ExecutionTestResult


def _discover_demo(temp_path: Path) -> MutationWorkspace:
    temp_path.mkdir(parents=True, exist_ok=True)
    package = temp_path / "calculator"
    tests = temp_path / "tests"
    package.mkdir()
    tests.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text(
        "def add(left, right):\n    return left + right\n",
        encoding="utf-8",
    )
    (tests / "test_core.py").write_text(
        "from calculator.core import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    return discover(temp_path)


def test_discovers_searches_and_summarizes_a_project(temp_path: Path) -> None:
    workspace = _discover_demo(temp_path)

    assert workspace.project.name == temp_path.name
    assert [package.name for package in workspace.find_packages("calc")] == ["calculator"]
    assert [module.name for module in workspace.find_modules("*core")] == ["calculator.core"]
    assert [chunk.function_name for chunk in workspace.find_chunks("calculator.core:add")] == ["add"]
    assert workspace.statistics().as_dict() == {
        "packages": 1,
        "modules": 1,
        "original_chunks": 1,
        "test_suites": 2,
        "test_cases": 1,
        "test_links": 2,
        "chunks_with_tests": 1,
        "requirements": 0,
    }
    assert str(workspace).startswith(f"MutationWorkspace(project={temp_path.name!r}")
    assert repr(workspace.find_modules("core")).startswith("[Module(name='calculator.core', path='calculator/core.py'")
    assert str(workspace.statistics()).startswith("ProjectStatistics(packages=1, modules=1")


def test_lists_resolves_and_applies_friendly_operator_names(temp_path: Path, capsys) -> None:
    workspace = _discover_demo(temp_path)
    module = workspace.find_modules("core")[0]

    mutants = workspace.mutate(module, ["arithmetic"], max_degree=1)

    assert mutants
    assert f"Generating mutants: {len(mutants)} new" in capsys.readouterr().out
    assert all(mutant.original is workspace.chunks[0] for mutant in mutants)
    assert workspace.find_mutants("add", degree=1) == mutants
    statistics = workspace.mutant_statistics()
    assert statistics.total == len(mutants)
    assert statistics.source_chunks == 1
    assert statistics.by_degree == {1: len(mutants)}
    assert statistics.by_type == {"arithmetic": len(mutants)}
    assert sum(statistics.by_operator.values()) == len(mutants)
    arithmetic_info = next(operator for operator in workspace.operators() if operator.name == "arithmetic")
    assert str(arithmetic_info) == "arithmetic: Replace one arithmetic binary operator."
    assert repr(arithmetic_info) == "OperatorInfo(name='arithmetic', class_name='ArithmeticMutation')"
    assert "MutantStatistics(total=" in repr(statistics)
    assert "CodeChunk(function_name='add', mutation_degree=1" in repr(mutants[0])
    assert available_operators() == sorted(available_operators(), key=lambda operator: operator.name)
    assert len(resolve_operators("all")) == len(available_operators())
    assert len(resolve_operators("*")) == len(available_operators())
    assert resolve_operators(arithmetic_info) == [arithmetic_info.operator_class]

    module_chunk_count = len(module.code_chunks)
    assert workspace.mutate(module, ["arithmetic"], max_degree=1) == []
    assert len(module.code_chunks) == module_chunk_count

    with pytest.raises(ValueError, match="unknown mutation operator"):
        workspace.mutate(module, ["does-not-exist"])


def test_can_mutate_only_chunks_with_related_tests(temp_path: Path) -> None:
    source = temp_path / "operations.py"
    source.write_text(
        "def add(left, right):\n"
        "    return left + right\n\n"
        "def subtract(left, right):\n"
        "    return left - right\n",
        encoding="utf-8",
    )
    tests = temp_path / "tests"
    tests.mkdir()
    (tests / "test_operations.py").write_text(
        "from operations import add\n\n\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    workspace = discover(temp_path)

    tested_chunks = workspace.chunks_with_tests()
    mutants = workspace.mutate_chunks_with_tests(workspace.chunks, "arithmetic", show_progress=False)

    assert [chunk.function_name for chunk in tested_chunks] == ["add"]
    assert mutants
    assert all(mutant.original is not None for mutant in mutants)
    assert {mutant.original.function_name for mutant in mutants if mutant.original is not None} == {"add"}
    assert workspace.find_mutants("subtract") == []
    assert workspace.chunks_with_tests(include_mutants=True) == [*tested_chunks, *mutants]


def test_adds_inputs_shows_tests_and_persists_the_workspace(temp_path: Path) -> None:
    workspace = _discover_demo(temp_path)
    original = workspace.chunks[0]
    mutant = workspace.mutate(original, ["arithmetic"])[0]

    function_input = workspace.add_input(mutant, (4, 5), label="add(4, 5)")
    text_input = workspace.add_text_input(original, '{"args": [2, 3]}')

    assert function_input.original_chunk is original
    assert text_input.original_chunk is original
    assert mutant.applicable_inputs == [function_input, text_input]
    assert [test.name for test in workspace.tests_for(mutant)] == ["tests.test_core.test_add"]

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        workspace.save(session, commit=True)
        assert len(session.scalars(select(CodeChunk)).all()) == 1 + len(workspace.mutants)
        assert len(session.scalars(select(FunctionInput)).all()) == 2


def test_rejects_targets_from_another_workspace(temp_path: Path) -> None:
    first = _discover_demo(temp_path / "first")
    second = _discover_demo(temp_path / "second")

    with pytest.raises(ValueError, match="does not belong"):
        first.mutate(second.chunks[0], ["arithmetic"])


def test_execution_helpers_default_to_generated_mutants(temp_path: Path, monkeypatch, capsys) -> None:
    workspace = _discover_demo(temp_path)
    mutants = workspace.mutate(workspace.chunks[0], ["arithmetic"])
    workspace.environment = PythonExecutionEnvironment(workspace.project, Path(sys.prefix))
    calls = []

    class FakeStandaloneExecution:
        def __init__(self, timeout_seconds: float) -> None:
            calls.append(("standalone", timeout_seconds))

        def execute_all(self, chunk, environment, *, extra_env=None):
            calls.append(("inputs", chunk, environment, extra_env))
            return []

    class FakeParallelExecution:
        def __init__(self, max_workers, timeout_seconds: float) -> None:
            calls.append(("parallel", max_workers, timeout_seconds))

        def execute_related_tests(
            self,
            chunks,
            environment,
            *,
            extra_env=None,
            on_chunk_complete=None,
            fallback_to_full_suite=True,
        ):
            calls.append(("tests", chunks, environment, extra_env))
            for completed, chunk in enumerate(chunks, start=1):
                if on_chunk_complete is not None:
                    on_chunk_complete(chunk, completed, len(chunks))
            return []

    monkeypatch.setattr("pymut4se.api.workspace.StandalonePythonExecution", FakeStandaloneExecution)
    monkeypatch.setattr("pymut4se.api.workspace.ParallelExecution", FakeParallelExecution)

    assert workspace.run_inputs(timeout_seconds=4) == []
    assert workspace.run_tests(max_workers=2, timeout_seconds=6) == []

    assert [call[1] for call in calls if call[0] == "inputs"] == mutants
    test_call = next(call for call in calls if call[0] == "tests")
    assert test_call[1] == mutants
    progress_output = capsys.readouterr().out
    assert f"Executing inputs: {len(mutants)}/{len(mutants)}" in progress_output
    assert f"Executing tests: {len(mutants)}/{len(mutants)}" in progress_output


def test_can_execute_tests_for_only_chunks_with_related_tests(temp_path: Path, monkeypatch) -> None:
    workspace = _discover_demo(temp_path)
    tested = workspace.chunks[0]
    untested = CodeChunk(
        "def noop():\n    return None\n",
        tested.module_id,
        "noop",
        "function",
        4,
        5,
        project_id=workspace.project.project_id,
    )
    tested.module.code_chunks.append(untested)
    workspace.project.code_chunks.append(untested)
    workspace.exploration.code_chunks.append(untested)
    calls = []

    def fake_run_tests(chunks, **kwargs):
        calls.append((chunks, kwargs))
        return []

    monkeypatch.setattr(workspace, "run_tests", fake_run_tests)

    assert workspace.run_tests_for_chunks_with_tests([tested, untested], parallel=False) == []

    selected, kwargs = calls[0]
    assert selected == [tested]
    assert kwargs["parallel"] is False
    assert kwargs["fallback_to_full_suite"] is False


def test_mutation_progress_is_cumulative_across_chunks(temp_path: Path, capsys) -> None:
    source = temp_path / "operations.py"
    source.write_text(
        "def add(left, right):\n    return left + right\n\ndef subtract(left, right):\n    return left - right\n",
        encoding="utf-8",
    )
    workspace = discover(source)

    mutants = workspace.mutate(workspace.chunks, "arithmetic")

    output = capsys.readouterr().out
    displayed_counts = [int(value) for value in re.findall(r"Generating mutants: (\d+) new", output)]
    assert displayed_counts == sorted(displayed_counts)
    assert displayed_counts[-1] == len(mutants)
    assert "chunks processed: 2/2" in output


def test_mutation_score_classifies_only_conclusive_test_results(temp_path: Path) -> None:
    workspace = _discover_demo(temp_path)
    mutants = workspace.mutate(workspace.chunks[0], "arithmetic", show_progress=False)[:4]
    test_case = workspace.tests_for(mutants[0])[0]
    environment_id = "test-environment"
    ExecutionTestResult(False, None, mutants[0], test_case, environment_id, return_code=1)
    ExecutionTestResult(True, {"stdout": "passed"}, mutants[1], test_case, environment_id, return_code=0)
    ExecutionTestResult(False, None, mutants[2], test_case, environment_id, return_code=2)

    score = workspace.mutation_score(mutants, environment_id=environment_id)

    assert score.as_dict() == {
        "total": 4,
        "assessed": 2,
        "killed": 1,
        "survived": 1,
        "untested": 1,
        "incomplete": 0,
        "errors": 1,
        "score": 0.5,
        "percentage": 50.0,
    }
    assert str(score) == ("MutationScore(score=50.00%, killed=1, survived=1, untested=1, incomplete=0, errors=1)")
    assert workspace.mutation_score([mutants[3]], environment_id=environment_id).score is None
