from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pymut4se.execution.environment import PythonExecutionEnvironment
from pymut4se.exploration.utils import EXCLUDED_DIRECTORY_NAMES
from pymut4se.model import (
    CodeChunk,
    ExecutionOutput,
    FunctionInput,
    Module,
    Project,
    TestCase,
    TestExecutionOutput,
)
from pymut4se.mutation import build_mutant

_RESULT_MARKER = "__PYMUT4SE_RESULT__"


@dataclass(frozen=True)
class _TestCasePlan:
    test_id: str
    node_id: str
    source_path: Path
    destination_path: Path


@dataclass(frozen=True)
class _TestProcessResult:
    success: bool
    output: object
    error_message: str
    return_code: Optional[int]
    time_taken: float


class StandalonePythonExecution:
    """Execute a chunk in its complete module using a prepared project venv."""

    def __init__(self, timeout_seconds: float = 2.0) -> None:
        if timeout_seconds <= 0:
            msg = "timeout_seconds must be greater than 0"
            raise ValueError(msg)
        self.timeout_seconds = timeout_seconds

    def execute(
        self,
        code_chunk: CodeChunk,
        function_input: FunctionInput,
        environment: PythonExecutionEnvironment,
        *,
        extra_env: Optional[dict[str, str]] = None,
    ) -> ExecutionOutput:
        """Run one input, or return its existing output for this environment."""
        if function_input not in code_chunk.applicable_inputs:
            msg = "function_input must apply to code_chunk"
            raise ValueError(msg)
        module, project = self._validate_execution_context(code_chunk, environment)
        existing = self._existing_execution(code_chunk, function_input, environment)
        if existing is not None:
            return existing

        with tempfile.TemporaryDirectory(prefix="pymut4se-execution-") as directory:
            workspace = Path(directory)
            harness_path = self._prepare_execution_workspace(code_chunk, module, project, workspace)
            return self._execute_in_workspace(
                code_chunk,
                function_input,
                environment,
                module,
                workspace,
                harness_path,
                extra_env,
            )

    def execute_all(
        self,
        code_chunk: CodeChunk,
        environment: PythonExecutionEnvironment,
        *,
        extra_env: Optional[dict[str, str]] = None,
    ) -> list[ExecutionOutput]:
        """Run every applicable input while building the mutant workspace once."""
        module, project = self._validate_execution_context(code_chunk, environment)
        inputs = list(code_chunk.applicable_inputs)
        outputs_by_input = {}
        pending_inputs = []
        for function_input in inputs:
            existing = self._existing_execution(code_chunk, function_input, environment)
            if existing is None:
                pending_inputs.append(function_input)
            else:
                outputs_by_input[function_input.input_id] = existing

        if pending_inputs:
            with tempfile.TemporaryDirectory(prefix="pymut4se-execution-") as directory:
                workspace = Path(directory)
                harness_path = self._prepare_execution_workspace(
                    code_chunk,
                    module,
                    project,
                    workspace,
                )
                for function_input in pending_inputs:
                    outputs_by_input[function_input.input_id] = self._execute_in_workspace(
                        code_chunk,
                        function_input,
                        environment,
                        module,
                        workspace,
                        harness_path,
                        extra_env,
                    )
        return [outputs_by_input[function_input.input_id] for function_input in inputs]

    def execute_related_tests(
        self,
        code_chunk: CodeChunk,
        environment: PythonExecutionEnvironment,
        *,
        extra_env: Optional[dict[str, str]] = None,
    ) -> list[TestExecutionOutput]:
        """Run every related test case against one shared mutant workspace."""
        module, project = self._validate_execution_context(code_chunk, environment)
        test_cases = list(code_chunk.related_test_cases)
        outputs_by_test = {}
        pending_tests = []
        for test_case in test_cases:
            existing = self._existing_test_execution(code_chunk, test_case, environment)
            if existing is None:
                pending_tests.append(test_case)
            else:
                outputs_by_test[test_case.test_id] = existing

        if pending_tests:
            with tempfile.TemporaryDirectory(prefix="pymut4se-test-execution-") as directory:
                workspace = Path(directory)
                self._prepare_execution_workspace(code_chunk, module, project, workspace)
                self._copy_test_suites(pending_tests, workspace)
                for test_case in pending_tests:
                    outputs_by_test[test_case.test_id] = self._execute_test_in_workspace(
                        code_chunk,
                        test_case,
                        environment,
                        workspace,
                        extra_env,
                    )
        return [outputs_by_test[test_case.test_id] for test_case in test_cases]

    @staticmethod
    def _validate_execution_context(
        code_chunk: CodeChunk,
        environment: PythonExecutionEnvironment,
    ) -> tuple[Module, Project]:
        if not environment.is_prepared:
            msg = "execution environment must be prepared before use"
            raise ValueError(msg)
        if not environment.is_current:
            msg = "execution environment requirements must be prepared before use"
            raise ValueError(msg)
        module = code_chunk.module
        if module is None:
            msg = "code_chunk must be attached to a module"
            raise ValueError(msg)
        project = module.project or code_chunk.project
        if project is None:
            msg = "code_chunk module must be attached to a project"
            raise ValueError(msg)
        if environment.project.project_id != project.project_id:
            msg = "execution environment must belong to the code chunk project"
            raise ValueError(msg)
        return module, project

    @staticmethod
    def _existing_execution(
        code_chunk: CodeChunk,
        function_input: FunctionInput,
        environment: PythonExecutionEnvironment,
    ) -> Optional[ExecutionOutput]:
        return next(
            (
                execution
                for execution in code_chunk.execution_outputs
                if execution.input_id == function_input.input_id
                and execution.environment_id == environment.environment_id
            ),
            None,
        )

    @staticmethod
    def _existing_test_execution(
        code_chunk: CodeChunk,
        test_case: TestCase,
        environment: PythonExecutionEnvironment,
    ) -> Optional[TestExecutionOutput]:
        return next(
            (
                execution
                for execution in code_chunk.test_execution_outputs
                if execution.test_id == test_case.test_id and execution.environment_id == environment.environment_id
            ),
            None,
        )

    def _prepare_execution_workspace(
        self,
        code_chunk: CodeChunk,
        module: Module,
        project: Project,
        workspace: Path,
    ) -> Path:
        self._prepare_workspace(project, workspace)
        _write_module_source(workspace, Path(module.path), build_mutant(code_chunk))
        harness_path = workspace / "_pymut4se_harness.py"
        harness_path.write_text(_HARNESS, encoding="utf-8")
        return harness_path

    def _execute_in_workspace(
        self,
        code_chunk: CodeChunk,
        function_input: FunctionInput,
        environment: PythonExecutionEnvironment,
        module: Module,
        workspace: Path,
        harness_path: Path,
        extra_env: Optional[dict[str, str]],
    ) -> ExecutionOutput:
        started_at = time.perf_counter()
        payload = json.dumps(
            {
                "function_name": code_chunk.function_name,
                "input_type": function_input.type,
                "input_value": function_input.value,
                "module_name": module.name,
            }
        )
        try:
            completed = subprocess.run(
                [str(environment.python_executable), str(harness_path)],
                input=payload,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                cwd=workspace,
                env=self._build_env(workspace, extra_env),
                check=False,
            )
            success = completed.returncode == 0
            if success:
                try:
                    output = _parse_output(completed.stdout)
                    error_message = ""
                except (json.JSONDecodeError, ValueError) as error:
                    success = False
                    output = _captured_output(completed.stdout)
                    error_message = str(error)
            else:
                output = _captured_output(completed.stdout)
                error_message = completed.stderr.strip()
        except subprocess.TimeoutExpired as error:
            success = False
            output = _captured_output(_timeout_text(error.stdout))
            error_message = f"execution timed out after {self.timeout_seconds} seconds"
        except OSError as error:
            success = False
            output = None
            error_message = str(error)

        return ExecutionOutput(
            success=success,
            output=output,
            code_chunk=code_chunk,
            function_input=function_input,
            environment_id=environment.environment_id,
            error_message=error_message,
            time_taken=time.perf_counter() - started_at,
        )

    def _execute_test_in_workspace(
        self,
        code_chunk: CodeChunk,
        test_case: TestCase,
        environment: PythonExecutionEnvironment,
        workspace: Path,
        extra_env: Optional[dict[str, str]],
    ) -> TestExecutionOutput:
        result = _run_test_case(
            _test_case_plan(test_case),
            environment.python_executable,
            workspace,
            self.timeout_seconds,
            extra_env,
        )

        return TestExecutionOutput(
            success=result.success,
            output=result.output,
            code_chunk=code_chunk,
            test_case=test_case,
            environment_id=environment.environment_id,
            error_message=result.error_message,
            return_code=result.return_code,
            time_taken=result.time_taken,
        )

    @staticmethod
    def _copy_test_suites(test_cases: list[TestCase], workspace: Path) -> None:
        _copy_test_case_sources([_test_case_plan(test_case) for test_case in test_cases], workspace)

    @staticmethod
    def _prepare_workspace(project: Project, workspace: Path) -> None:
        _copy_project_source(_project_source_path(project), workspace)

    @staticmethod
    def _build_env(workspace: Path, extra_env: Optional[dict[str, str]]) -> dict[str, str]:
        return _build_subprocess_env(workspace, extra_env)


# Backward-compatible shorter name.  Keep the Python-specific name canonical so
# generated documentation and tracebacks match the public API used in examples.
StandaloneExecution = StandalonePythonExecution


def _project_source_path(project: Project) -> Path:
    return Path(project.absolute_path or project.path).expanduser().resolve()


def _copy_project_source(source: Path, workspace: Path) -> None:
    if not source.exists():
        msg = f"project source path does not exist: {source}"
        raise FileNotFoundError(msg)
    if source.is_file():
        shutil.copy2(source, workspace / source.name)
        return
    shutil.copytree(
        source,
        workspace,
        dirs_exist_ok=True,
        ignore=_ignored_project_entries,
    )


def _write_module_source(workspace: Path, module_path: Path, module_source: str) -> None:
    destination = workspace / module_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(module_source, encoding="utf-8")


def _test_case_plan(test_case: TestCase) -> _TestCasePlan:
    suite = test_case.suite
    if not suite.absolute_path:
        msg = f"test suite has no source path: {suite.name}"
        raise ValueError(msg)
    return _TestCasePlan(
        test_id=test_case.test_id,
        node_id=_pytest_node_id(test_case),
        source_path=Path(suite.absolute_path),
        destination_path=Path(suite.path),
    )


def _copy_test_case_sources(test_cases: list[_TestCasePlan], workspace: Path) -> None:
    copied_paths = set()
    for test_case in test_cases:
        if test_case.destination_path in copied_paths:
            continue
        copied_paths.add(test_case.destination_path)
        if not test_case.source_path.is_file():
            msg = f"test suite source path does not exist: {test_case.source_path}"
            raise FileNotFoundError(msg)
        destination = workspace / test_case.destination_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(test_case.source_path, destination)


def _build_subprocess_env(
    workspace: Path,
    extra_env: Optional[dict[str, str]],
) -> dict[str, str]:
    environment = os.environ.copy()
    existing_python_path = environment.get("PYTHONPATH", "")
    source_directory = workspace / "src"
    environment["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (
            str(workspace),
            str(source_directory) if source_directory.is_dir() else "",
            existing_python_path,
        )
        if value
    )
    if extra_env:
        environment.update({key: str(value) for key, value in extra_env.items()})
    return environment


def _run_test_case(
    test_case: _TestCasePlan,
    python_executable: Path,
    workspace: Path,
    timeout_seconds: float,
    extra_env: Optional[dict[str, str]],
) -> _TestProcessResult:
    started_at = time.perf_counter()
    try:
        completed = subprocess.run(
            [str(python_executable), "-m", "pytest", test_case.node_id, "-q"],
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            cwd=workspace,
            env=_build_subprocess_env(workspace, extra_env),
            check=False,
        )
        return _TestProcessResult(
            success=completed.returncode == 0,
            output=_captured_output(completed.stdout),
            error_message=completed.stderr.strip(),
            return_code=completed.returncode,
            time_taken=time.perf_counter() - started_at,
        )
    except subprocess.TimeoutExpired as error:
        return _TestProcessResult(
            success=False,
            output=_captured_output(_timeout_text(error.stdout)),
            error_message=f"test execution timed out after {timeout_seconds} seconds",
            return_code=None,
            time_taken=time.perf_counter() - started_at,
        )
    except OSError as error:
        return _TestProcessResult(
            success=False,
            output=None,
            error_message=str(error),
            return_code=None,
            time_taken=time.perf_counter() - started_at,
        )


def _ignored_project_entries(_directory: str, names: list[str]) -> list[str]:
    return [name for name in names if name.lower() in EXCLUDED_DIRECTORY_NAMES]


def _pytest_node_id(test_case: TestCase) -> str:
    suite_prefix = f"{test_case.suite.name}."
    qualified_name = test_case.name.removeprefix(suite_prefix)
    case_path = "::".join(qualified_name.split("."))
    return f"{Path(test_case.suite.path).as_posix()}::{case_path}"


def _parse_output(stdout: str) -> object:
    lines = stdout.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        if not line.startswith(_RESULT_MARKER):
            continue
        result = json.loads(line[len(_RESULT_MARKER) :])
        preceding_output = "\n".join(lines[:index]).strip()
        if preceding_output:
            result["stdout"] = preceding_output
        return result
    msg = "execution completed without a PyMut4SE result"
    raise ValueError(msg)


def _captured_output(stdout: str) -> object:
    captured = stdout.strip()
    return {"stdout": captured} if captured else None


def _timeout_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


_HARNESS = f'''\
import ast
import base64
import importlib
import json
import pickle
import sys


def decode_text(value):
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        expression = ast.parse(value, mode="eval").body
        if isinstance(expression, ast.Call):
            return (
                [ast.literal_eval(argument) for argument in expression.args],
                {{keyword.arg: ast.literal_eval(keyword.value) for keyword in expression.keywords}},
            )
        decoded = ast.literal_eval(value)
    if isinstance(decoded, dict) and ("args" in decoded or "kwargs" in decoded):
        return decoded.get("args", []), decoded.get("kwargs", {{}})
    if isinstance(decoded, (list, tuple)):
        return list(decoded), {{}}
    return [decoded], {{}}


payload = json.loads(sys.stdin.read())
module = importlib.import_module(payload["module_name"])
function = module
for component in payload["function_name"].split("."):
    function = getattr(function, component)
if payload["input_type"] == "serialized":
    arguments = pickle.loads(base64.b64decode(payload["input_value"]))
    keyword_arguments = {{}}
else:
    arguments, keyword_arguments = decode_text(payload["input_value"])
result = function(*arguments, **keyword_arguments)
print("{_RESULT_MARKER}" + json.dumps({{"result": result}}, default=str))
'''
