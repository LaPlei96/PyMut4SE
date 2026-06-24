from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from pymut4se.execution.environment import PythonExecutionEnvironment
from pymut4se.execution.standalone_execution import (
    StandalonePythonExecution,
    _TestCasePlan,
    _TestProcessResult,
    _copy_project_source,
    _copy_test_case_sources,
    _project_source_path,
    _run_test_case,
    _test_case_plan,
    _write_module_source,
)
from pymut4se.model import CodeChunk, TestCase, TestExecutionOutput
from pymut4se.mutation import build_mutant


@dataclass(frozen=True)
class _ChunkTestPlan:
    chunk_id: str
    module_path: Path
    module_source: str
    project_source: Path
    test_cases: tuple[_TestCasePlan, ...]


@dataclass(frozen=True)
class _ChunkTestResults:
    chunk_id: str
    results: tuple[tuple[str, _TestProcessResult], ...]


class ParallelExecution:
    """Execute related tests for several chunks with bounded concurrency."""

    def __init__(self, max_workers: Optional[int] = None, timeout_seconds: float = 2.0) -> None:
        if max_workers is not None and max_workers < 1:
            msg = "max_workers must be greater than or equal to 1"
            raise ValueError(msg)
        self.max_workers = max_workers or min(8, os.cpu_count() or 1)
        self.standalone = StandalonePythonExecution(timeout_seconds=timeout_seconds)

    def execute_related_tests(
        self,
        code_chunks: Sequence[CodeChunk],
        environment: PythonExecutionEnvironment,
        *,
        extra_env: Optional[dict[str, str]] = None,
        on_chunk_complete: Optional[Callable[[CodeChunk, int, int], None]] = None,
        fallback_to_full_suite: bool = True,
    ) -> list[TestExecutionOutput]:
        """Run missing chunk/test pairs in parallel and attach results centrally."""
        chunks = list({chunk.chunk_id: chunk for chunk in code_chunks}.values())
        outputs: dict[tuple[str, str], TestExecutionOutput] = {}
        tests_by_key: dict[tuple[str, str], TestCase] = {}
        selected_tests_by_chunk: dict[str, list[TestCase]] = {}
        plans = []
        completed_chunks = 0

        for code_chunk in chunks:
            module, project = self.standalone._validate_execution_context(code_chunk, environment)
            test_cases = self.standalone._test_cases_for_execution(
                code_chunk,
                project,
                fallback_to_full_suite=fallback_to_full_suite,
            )
            selected_tests_by_chunk[code_chunk.chunk_id] = test_cases
            pending_tests = []
            for test_case in test_cases:
                key = (code_chunk.chunk_id, test_case.test_id)
                tests_by_key[key] = test_case
                existing = self.standalone._existing_test_execution(
                    code_chunk,
                    test_case,
                    environment,
                )
                if existing is None:
                    pending_tests.append(test_case)
                else:
                    outputs[key] = existing
            if pending_tests:
                plans.append(
                    _ChunkTestPlan(
                        chunk_id=code_chunk.chunk_id,
                        module_path=Path(module.path),
                        module_source=build_mutant(code_chunk),
                        project_source=_project_source_path(project),
                        test_cases=tuple(_test_case_plan(test_case) for test_case in pending_tests),
                    )
                )
            else:
                completed_chunks += 1
                if on_chunk_complete is not None:
                    on_chunk_complete(code_chunk, completed_chunks, len(chunks))

        chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        if plans:
            worker_count = min(self.max_workers, len(plans))
            with ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="pymut4se-tests",
            ) as executor:
                futures = {
                    executor.submit(
                        _execute_chunk_plan,
                        plan,
                        environment.python_executable,
                        self.standalone.timeout_seconds,
                        extra_env,
                    ): plan.chunk_id
                    for plan in plans
                }
                for future in as_completed(futures):
                    chunk_results = future.result()
                    code_chunk = chunks_by_id[chunk_results.chunk_id]
                    for test_id, result in chunk_results.results:
                        test_case = tests_by_key[(chunk_results.chunk_id, test_id)]
                        outputs[(chunk_results.chunk_id, test_id)] = TestExecutionOutput(
                            success=result.success,
                            output=result.output,
                            code_chunk=code_chunk,
                            test_case=test_case,
                            environment_id=environment.environment_id,
                            error_message=result.error_message,
                            return_code=result.return_code,
                            time_taken=result.time_taken,
                        )
                    completed_chunks += 1
                    if on_chunk_complete is not None:
                        on_chunk_complete(code_chunk, completed_chunks, len(chunks))

        return [
            outputs[(chunk.chunk_id, test_case.test_id)]
            for chunk in chunks
            for test_case in selected_tests_by_chunk[chunk.chunk_id]
        ]


def execute_related_tests_parallel(
    code_chunks: Sequence[CodeChunk],
    environment: PythonExecutionEnvironment,
    *,
    max_workers: Optional[int] = None,
    timeout_seconds: float = 2.0,
    extra_env: Optional[dict[str, str]] = None,
    on_chunk_complete: Optional[Callable[[CodeChunk, int, int], None]] = None,
    fallback_to_full_suite: bool = True,
) -> list[TestExecutionOutput]:
    """Convenience wrapper for bounded parallel related-test execution."""
    return ParallelExecution(
        max_workers=max_workers,
        timeout_seconds=timeout_seconds,
    ).execute_related_tests(
        code_chunks,
        environment,
        extra_env=extra_env,
        on_chunk_complete=on_chunk_complete,
        fallback_to_full_suite=fallback_to_full_suite,
    )


def _execute_chunk_plan(
    plan: _ChunkTestPlan,
    python_executable: Path,
    timeout_seconds: float,
    extra_env: Optional[dict[str, str]],
) -> _ChunkTestResults:
    with tempfile.TemporaryDirectory(prefix="pymut4se-parallel-tests-") as directory:
        workspace = Path(directory)
        _copy_project_source(plan.project_source, workspace)
        _write_module_source(workspace, plan.module_path, plan.module_source)
        _copy_test_case_sources(list(plan.test_cases), workspace)
        results = tuple(
            (
                test_case.test_id,
                _run_test_case(
                    test_case,
                    python_executable,
                    workspace,
                    timeout_seconds,
                    extra_env,
                ),
            )
            for test_case in plan.test_cases
        )
    return _ChunkTestResults(chunk_id=plan.chunk_id, results=results)
