import sys
import threading
from pathlib import Path

import pytest

from pymut4se.execution import (
    ParallelExecution,
    PythonExecutionEnvironment,
    execute_related_tests_parallel,
)
from pymut4se.exploration import explore_path
from pymut4se.model import CodeChunk
from pymut4se.mutation import build_mutant
from pymut4se.mutation.generic import ArithmeticMutation


def _parallel_graph(temp_path: Path):
    source_path = temp_path / "src"
    tests_path = temp_path / "tests"
    source_path.mkdir()
    tests_path.mkdir()
    (source_path / "application.py").write_text(
        "def add(left, right):\n    return left + right\n",
        encoding="utf-8",
    )
    (tests_path / "test_application.py").write_text(
        "from application import add\n\ndef test_add():\n    assert add(3, 2) == 5\n",
        encoding="utf-8",
    )
    result = explore_path(source_path)
    original = result.code_chunks[0]
    mutants = [
        mutant for mutant in ArithmeticMutation().mutate(original) if mutant.mutation_operator in {"Sub", "Mult"}
    ]
    return result.project, mutants


def test_executes_chunks_concurrently_and_creates_models_on_the_main_thread(
    temp_path: Path,
    monkeypatch,
) -> None:
    project, mutants = _parallel_graph(temp_path)
    environment = PythonExecutionEnvironment(project, Path(sys.prefix))
    import pymut4se.execution.parallel_execution as parallel_module

    original_worker = parallel_module._execute_chunk_plan
    original_output_model = parallel_module.TestExecutionOutput
    barrier = threading.Barrier(2)
    worker_threads = set()
    model_threads = []

    def synchronized_worker(*args, **kwargs):
        worker_threads.add(threading.current_thread().name)
        barrier.wait(timeout=5)
        return original_worker(*args, **kwargs)

    def tracked_output_model(*args, **kwargs):
        model_threads.append(threading.current_thread().name)
        return original_output_model(*args, **kwargs)

    monkeypatch.setattr(parallel_module, "_execute_chunk_plan", synchronized_worker)
    monkeypatch.setattr(parallel_module, "TestExecutionOutput", tracked_output_model)

    outputs = ParallelExecution(max_workers=2).execute_related_tests(mutants, environment)

    assert len(outputs) == 2
    assert all(not output.success for output in outputs)
    assert len(worker_threads) == 2
    assert all(name.startswith("pymut4se-tests") for name in worker_threads)
    assert model_threads == [threading.main_thread().name] * 2


def test_parallel_execution_reuses_cached_results_without_rebuilding(
    temp_path: Path,
    monkeypatch,
) -> None:
    project, mutants = _parallel_graph(temp_path)
    environment = PythonExecutionEnvironment(project, Path(sys.prefix))
    build_calls = 0

    def counted_build(code_chunk: CodeChunk) -> str:
        nonlocal build_calls
        build_calls += 1
        return build_mutant(code_chunk)

    monkeypatch.setattr(
        "pymut4se.execution.parallel_execution.build_mutant",
        counted_build,
    )
    executor = ParallelExecution(max_workers=2)

    first_run = executor.execute_related_tests(mutants, environment)
    second_run = executor.execute_related_tests(mutants, environment)

    assert second_run == first_run
    assert build_calls == 2
    assert all(len(mutant.test_execution_outputs) == 1 for mutant in mutants)


def test_parallel_convenience_function_and_validation(temp_path: Path) -> None:
    project, mutants = _parallel_graph(temp_path)
    environment = PythonExecutionEnvironment(project, Path(sys.prefix))

    outputs = execute_related_tests_parallel(mutants[:1], environment, max_workers=1)

    assert len(outputs) == 1
    with pytest.raises(ValueError, match="max_workers must be greater than or equal to 1"):
        ParallelExecution(max_workers=0)
