# Standalone Python execution

PyMut4SE executes an original or mutant `CodeChunk` from within its complete
module. Execution uses a reusable virtual environment prepared for the explored
project rather than the Python process running PyMut4SE.

## Preparing a reusable environment

```python
from pymut4se.execution import PythonExecutionEnvironment

environment = PythonExecutionEnvironment.for_project(project)
environment.prepare()
```

By default, the venv is stored under `.pymut4se/venvs/<project_id>` and is
excluded from project exploration and execution workspace copies. A different
parent directory can be supplied with `environments_root`.

The first preparation creates the venv using the current system Python. For an
existing `requirements.txt`, installation uses `pip install -r` so file options
and included requirement files are preserved. For `pyproject.toml` or an
unavailable manifest, installation falls back to
`project.get_requirement_strings()`.

Pytest is installed as execution infrastructure after project dependencies, even
when the project has no dependency manifest and does not declare pytest itself.
Preparation verifies that pytest can actually be imported from the venv; an
existing incomplete environment is repaired even when its dependency
fingerprint has not changed.

A requirements fingerprint is stored inside the environment. Later calls reuse
the venv without reinstalling unchanged dependencies. Pass
`refresh_requirements=True` to force installation again.

## Executing a chunk

```python
from pymut4se.execution import StandalonePythonExecution

executor = StandalonePythonExecution(timeout_seconds=2)
execution = executor.execute(
    mutant,
    function_input,
    environment,
)
```

If that chunk/input pair already has an `ExecutionOutput` for
`environment.environment_id`, `execute()` returns it without copying the project
or starting Python again. The environment identity includes its project, path,
system interpreter, and requirement fingerprint.

Run every input applicable to a chunk with one shared workspace and module build:

```python
executions = executor.execute_all(mutant, environment)
```

Cached results are returned in input order. Only missing input/environment pairs
are executed, and all missing pairs reuse the same copied project, substituted
module, and harness.

## Executing related tests

Every original chunk exposes its inferred test cases through
`related_test_cases`; mutants expose the same cases through their degree-zero
original. Execute all of them with:

```python
test_executions = executor.execute_related_tests(mutant, environment)
```

When no related cases were inferred, execution falls back to every discovered
test case in the project. Disable that behavior with
`fallback_to_full_suite=False` when an empty result is preferable to the cost of
running the full suite.

The project and substituted module are built once. Test files—including sibling
`tests/` directories discovered when exploring `src/`—are copied from their
stored paths, then each case is selected with its precise pytest node ID. This
supports top-level tests and class-based test methods.

Existing `TestExecutionOutput` rows for the same chunk, test case, and
environment are returned without invoking pytest again. Results include pytest's
return code, captured output, errors, and timing and can be navigated through
`chunk.test_execution_outputs` or `test_case.execution_outputs`.

## Executing tests across chunks in parallel

Use `ParallelExecution` when several originals or mutants should be tested:

```python
from pymut4se.execution import ParallelExecution

executor = ParallelExecution(max_workers=4, timeout_seconds=2)
test_executions = executor.execute_related_tests(mutants, environment)
```

The convenience function provides the same operation:

```python
from pymut4se.execution import execute_related_tests_parallel

test_executions = execute_related_tests_parallel(
    mutants,
    environment,
    max_workers=4,
)
```

Each worker handles one chunk at a time, with one isolated workspace and one
module build reused across that chunk's tests. The prepared venv is shared
read-only. Cache resolution, ORM relationship access, and
`TestExecutionOutput` construction stay on the calling thread; workers receive
immutable file/test plans and return plain result values. This keeps SQLAlchemy
sessions out of worker threads and lets SQLite persistence remain centralized.

Results are returned in chunk order and then related-test order. Duplicate chunks
and already cached chunk/test/environment combinations are not scheduled. The
default pool is capped at eight workers and can be reduced for projects whose
tests consume substantial CPU or memory.

The executor:

1. Checks that the venv and its requirements are current for the chunk's project
   and that the input applies to the chunk.
2. Copies the explored project into a temporary workspace while excluding
   environments, caches, and build output.
3. Uses `build_mutant()` to substitute the selected chunk into its complete
   module.
4. Imports that module inside the prepared venv and calls the chunk's qualified
   function name.
5. Returns a connected `ExecutionOutput` containing the JSON result, captured
   standard output, errors, and elapsed time.

Serialized `FunctionInput` values provide a positional-argument tuple. Text
inputs accept JSON arguments, Python literal collections, or a literal call such
as `add(1, 2)`. Dotted names such as static or class members are resolved through
module attributes; ordinary instance methods still require an appropriate
receiver argument.

## Persistence and safety

The returned output is already linked through `execution.code_chunk` and
`execution.function_input`. Add newly returned outputs explicitly with
`session.add_all(outputs)` before committing. This is especially important when
the surrounding project was persisted before the executions were created.

Execution runs arbitrary project code and may install arbitrary project
dependencies. Only prepare and execute projects and serialized inputs that you
trust. Timeouts stop long-running function calls, but a virtual environment is
not a security sandbox.
