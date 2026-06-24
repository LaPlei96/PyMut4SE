import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.execution import PythonExecutionEnvironment, StandalonePythonExecution
from pymut4se.exploration import explore_path
from pymut4se.model import Base, CodeChunk, Project
from pymut4se.model import TestExecutionOutput as ModelTestExecutionOutput
from pymut4se.mutation import build_mutant
from pymut4se.mutation.generic import ArithmeticMutation


def _explored_project(temp_path: Path):
    source_path = temp_path / "src"
    tests_path = temp_path / "tests"
    source_path.mkdir()
    tests_path.mkdir()
    (source_path / "application.py").write_text(
        "def add(left, right):\n    return left + right\n\ndef other():\n    return None\n",
        encoding="utf-8",
    )
    (tests_path / "test_application.py").write_text(
        "from application import add\n\n"
        "class TestAdd:\n"
        "    def test_positive(self):\n"
        "        assert add(2, 1) == 3\n\n"
        "def test_negative():\n"
        "    assert add(-2, -1) == -3\n",
        encoding="utf-8",
    )
    return explore_path(source_path)


def test_chunk_and_mutant_resolve_the_same_related_test_cases(temp_path: Path) -> None:
    result = _explored_project(temp_path)
    original = result.code_chunks[0]
    mutant = next(item for item in ArithmeticMutation().mutate(original) if item.mutation_operator == "Sub")

    assert [test.name.split(".")[-1] for test in original.related_test_cases] == [
        "test_positive",
        "test_negative",
    ]
    assert mutant.related_test_cases == original.related_test_cases


def test_executes_all_related_tests_with_one_build_and_caches_results(
    temp_path: Path,
    monkeypatch,
) -> None:
    result = _explored_project(temp_path)
    original = result.code_chunks[0]
    environment = PythonExecutionEnvironment(result.project, Path(sys.prefix))
    executor = StandalonePythonExecution()
    build_calls = 0

    def counted_build(code_chunk: CodeChunk) -> str:
        nonlocal build_calls
        build_calls += 1
        return build_mutant(code_chunk)

    monkeypatch.setattr(
        "pymut4se.execution.standalone_execution.build_mutant",
        counted_build,
    )

    first_run = executor.execute_related_tests(original, environment)
    cached_run = executor.execute_related_tests(original, environment)

    assert len(first_run) == 2
    assert all(execution.success for execution in first_run)
    assert all(execution.return_code == 0 for execution in first_run)
    assert all(execution.environment_id == environment.environment_id for execution in first_run)
    assert all(execution.code_chunk is original for execution in first_run)
    assert cached_run == first_run
    assert build_calls == 1
    assert original.test_execution_outputs == first_run


def test_related_tests_observe_the_mutated_module_and_outputs_persist(temp_path: Path) -> None:
    result = _explored_project(temp_path)
    original = result.code_chunks[0]
    mutant = next(item for item in ArithmeticMutation().mutate(original) if item.mutation_operator == "Sub")
    environment = PythonExecutionEnvironment(result.project, Path(sys.prefix))

    executions = StandalonePythonExecution().execute_related_tests(mutant, environment)

    assert len(executions) == 2
    assert all(not execution.success for execution in executions)
    assert all(execution.return_code == 1 for execution in executions)
    assert all(execution.output and "failed" in execution.output["stdout"] for execution in executions)

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(result.project)
        session.commit()
        session.expire_all()

        stored = session.get(ModelTestExecutionOutput, executions[0].execution_id)
        stored_project = session.get(Project, result.project.project_id)
        assert stored is not None
        assert stored_project is not None
        assert stored.code_chunk.chunk_id == mutant.chunk_id
        assert stored.test_case.test_id == executions[0].test_id
        assert stored in stored.test_case.execution_outputs


def test_chunk_without_related_tests_runs_the_full_suite_by_default(temp_path: Path) -> None:
    result = _explored_project(temp_path)
    unrelated = next(chunk for chunk in result.code_chunks if chunk.function_name == "other")
    environment = PythonExecutionEnvironment(result.project, Path(sys.prefix))

    executions = StandalonePythonExecution().execute_related_tests(unrelated, environment)

    assert len(executions) == len(result.test_cases) == 2
    assert all(execution.success for execution in executions)

    assert (
        StandalonePythonExecution().execute_related_tests(
            unrelated,
            environment,
            fallback_to_full_suite=False,
        )
        == []
    )
