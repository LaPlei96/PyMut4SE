import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.execution import PythonExecutionEnvironment, StandalonePythonExecution
from pymut4se.model import Base, CodeChunk, FunctionInput, Module, Project
from pymut4se.mutation import build_mutant


def _project_graph(temp_path: Path) -> tuple[Project, CodeChunk, CodeChunk, FunctionInput]:
    source = "def add(left, right):\n    return left + right\n"
    (temp_path / "application.py").write_text(source, encoding="utf-8")
    project = Project("demo", ".", absolute_path=temp_path.as_posix())
    module = Module("application", "application.py", source=source)
    original = CodeChunk(source, module.module_id, "add", "function", 1, 2)
    mutant = CodeChunk(
        "def add(left, right):\n    return left - right",
        module.module_id,
        "add",
        "function",
        1,
        2,
        mutation_degree=1,
        original_id=original.chunk_id,
        parent_id=original.chunk_id,
    )
    mutant.parent = original
    mutant.original = original
    module.code_chunks.extend([original, mutant])
    project.modules.append(module)
    project.code_chunks.extend([original, mutant])
    function_input = FunctionInput.from_value((7, 2), "add(7, 2)", original_chunk=original)
    return project, original, mutant, function_input


def test_executes_a_mutant_from_within_its_complete_module(temp_path: Path) -> None:
    project, _, mutant, function_input = _project_graph(temp_path)
    environment = PythonExecutionEnvironment(project=project, path=Path(sys.prefix))

    execution = StandalonePythonExecution().execute(mutant, function_input, environment)

    assert execution.success
    assert execution.output == {"result": 5}
    assert execution.error_message == ""
    assert execution.time_taken > 0
    assert execution.code_chunk is mutant
    assert execution.function_input is function_input
    assert execution.environment_id == environment.environment_id

    cached = StandalonePythonExecution().execute(mutant, function_input, environment)
    assert cached is execution
    assert mutant.execution_outputs == [execution]


def test_executes_text_inputs_and_preserves_function_stdout(temp_path: Path) -> None:
    source = "def greet(greeting, name):\n    print('called café')\n    return f'{greeting}, {name}'\n"
    (temp_path / "application.py").write_text(source, encoding="utf-8")
    project = Project("demo", ".", absolute_path=temp_path.as_posix())
    module = Module("application", "application.py", source=source)
    chunk = CodeChunk(source, module.module_id, "greet", "function", 1, 3)
    module.code_chunks.append(chunk)
    project.modules.append(module)
    project.code_chunks.append(chunk)
    function_input = FunctionInput.from_text_representation(
        "greet('Hello', 'Ada')",
        original_chunk=chunk,
    )
    environment = PythonExecutionEnvironment(project=project, path=Path(sys.prefix))

    execution = StandalonePythonExecution().execute(chunk, function_input, environment)

    assert execution.success
    assert execution.output == {"result": "Hello, Ada", "stdout": "called café"}


def test_requires_a_prepared_matching_environment_and_applicable_input(temp_path: Path) -> None:
    project, original, mutant, function_input = _project_graph(temp_path)
    unprepared = PythonExecutionEnvironment(project=project, path=temp_path / "missing-venv")
    other_project = Project("other", "other", absolute_path=temp_path.as_posix())
    mismatched = PythonExecutionEnvironment(project=other_project, path=Path(sys.prefix))
    unrelated = CodeChunk(
        "def other():\n    return None",
        "other-module",
        "other",
        "function",
        1,
        2,
    )
    executor = StandalonePythonExecution()

    with pytest.raises(ValueError, match="must be prepared"):
        executor.execute(mutant, function_input, unprepared)
    with pytest.raises(ValueError, match="must belong to the code chunk project"):
        executor.execute(mutant, function_input, mismatched)
    with pytest.raises(ValueError, match="function_input must apply"):
        executor.execute(unrelated, function_input, PythonExecutionEnvironment(project, Path(sys.prefix)))

    assert original.execution_outputs == []


def test_executes_all_inputs_with_one_module_build_and_reuses_cached_outputs(
    temp_path: Path,
    monkeypatch,
) -> None:
    project, original, mutant, first_input = _project_graph(temp_path)
    second_input = FunctionInput.from_value((10, 3), "add(10, 3)", original_chunk=original)
    environment = PythonExecutionEnvironment(project=project, path=Path(sys.prefix))
    build_calls = 0

    def counted_build(code_chunk: CodeChunk) -> str:
        nonlocal build_calls
        build_calls += 1
        return build_mutant(code_chunk)

    monkeypatch.setattr(
        "pymut4se.execution.standalone_execution.build_mutant",
        counted_build,
    )
    executor = StandalonePythonExecution()

    first_run = executor.execute_all(mutant, environment)
    second_run = executor.execute_all(mutant, environment)

    assert [execution.output for execution in first_run] == [{"result": 5}, {"result": 7}]
    assert second_run == first_run
    assert first_run[0].function_input is first_input
    assert first_run[1].function_input is second_input
    assert build_calls == 1
    assert len(mutant.execution_outputs) == 2


def test_reuses_a_persisted_execution_without_rebuilding_the_workspace(
    temp_path: Path,
    monkeypatch,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    project, _, mutant, function_input = _project_graph(temp_path)
    environment = PythonExecutionEnvironment(project=project, path=Path(sys.prefix))
    executor = StandalonePythonExecution()
    execution = executor.execute(mutant, function_input, environment)

    with Session(engine) as session:
        session.add(project)
        session.commit()
        session.expire_all()

        stored_project = session.get(Project, project.project_id)
        stored_mutant = session.get(CodeChunk, mutant.chunk_id)
        assert stored_project is not None
        assert stored_mutant is not None
        stored_environment = PythonExecutionEnvironment(stored_project, Path(sys.prefix))

        def fail_if_rebuilt(_project: Project, _workspace: Path) -> None:
            raise AssertionError("cached execution should not rebuild the workspace")

        monkeypatch.setattr(executor, "_prepare_workspace", fail_if_rebuilt)
        cached = executor.execute(
            stored_mutant,
            stored_mutant.applicable_inputs[0],
            stored_environment,
        )

        assert cached.execution_id == execution.execution_id


def test_rejects_non_positive_timeouts() -> None:
    with pytest.raises(ValueError, match="timeout_seconds must be greater than 0"):
        StandalonePythonExecution(timeout_seconds=0)
