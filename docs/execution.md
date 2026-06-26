# Execution And Environments

PyMut4SE executes originals and mutants in a reusable virtual environment for
the explored project. The Python process running PyMut4SE is not used to run the
target code.

Most users should execute through the workspace:

```python
outputs = workspace.run_tests_for_chunks_with_tests(mutants, max_workers=4)
score = workspace.mutation_score(mutants)
```

Use the lower-level execution classes when you need direct control over
environments, individual inputs, or individual test cases.

## Prepare An Environment

```python
from pymut4se.execution import PythonExecutionEnvironment

environment = PythonExecutionEnvironment.for_project(project)
environment.prepare()
```

By default, the virtual environment lives under:

```text
.pymut4se/venvs/<project_id>
```

Preparation:

- creates the environment with the current system Python;
- installs project dependencies;
- installs pytest as execution infrastructure;
- verifies that pytest can be imported;
- stores a dependency fingerprint so unchanged requirements are not reinstalled.

Pass `refresh_requirements=True` to force dependency installation again:

```python
environment.prepare(refresh_requirements=True)
```

Execution installs dependencies and runs arbitrary target project code. Only use
projects you trust.

## Run Function Inputs

Create a standalone executor:

```python
from pymut4se.execution import StandalonePythonExecution

executor = StandalonePythonExecution(timeout_seconds=2)
```

Run one chunk with one input:

```python
execution = executor.execute(mutant, function_input, environment)
```

Run every input applicable to a chunk:

```python
executions = executor.execute_all(mutant, environment)
```

`execute_all()` builds the temporary project workspace once and reuses it for
all missing input executions. Cached results for the same chunk, input, and
environment are returned without running Python again.

## Run Related Tests

Every original chunk exposes inferred tests through `related_test_cases`.
Mutants expose the same tests through their degree-zero original.

```python
test_outputs = executor.execute_related_tests(mutant, environment)
```

At the lower execution layer, if no related tests were inferred, execution falls
back to every discovered test case in the project. Disable fallback when an
empty result is preferable:

```python
test_outputs = executor.execute_related_tests(
    mutant,
    environment,
    fallback_to_full_suite=False,
)
```

The high-level workspace defaults are stricter: `workspace.run_tests()` does not
fall back unless `fallback_to_full_suite=True`, and
`workspace.run_tests_for_chunks_with_tests()` skips untested chunks entirely.

## Run Tests In Parallel

Use `ParallelExecution` for several originals or mutants:

```python
from pymut4se.execution import ParallelExecution

executor = ParallelExecution(max_workers=4, timeout_seconds=20)
test_outputs = executor.execute_related_tests(mutants, environment)
```

The convenience function performs the same operation:

```python
from pymut4se.execution import execute_related_tests_parallel

test_outputs = execute_related_tests_parallel(
    mutants,
    environment,
    max_workers=4,
)
```

Each worker gets an isolated project copy and reuses the prepared environment
read-only. SQLAlchemy relationship access and output model construction stay on
the calling thread, so sessions do not cross worker boundaries.

Results are returned in chunk order and then related-test order. Duplicate
chunks and cached chunk/test/environment combinations are not scheduled again.

## What Happens During Execution

For each chunk, PyMut4SE:

1. validates that the environment belongs to the same project;
2. copies the explored project into a temporary workspace;
3. uses `build_mutant()` to substitute the selected chunk into its full module;
4. runs either the function harness or pytest inside the prepared environment;
5. returns connected `ExecutionOutput` or `TestExecutionOutput` models.

Test execution copies the discovered test files and selects each case by its
pytest node ID. This supports top-level tests and class-based test methods.

## Inputs

Serialized `FunctionInput` values provide a positional-argument tuple:

```python
workspace.add_input(chunk, (1, 2), label="add(1, 2)")
```

Text inputs can be JSON, Python literal collections, or literal calls:

```python
workspace.add_text_input(chunk, '{"args": [1, 2]}')
workspace.add_text_input(chunk, "add(1, 2)")
```

Serialized inputs use Python pickle and must be treated as trusted data.

## Persistence

Returned outputs are linked to their chunks, inputs, tests, and environment.
Add newly returned outputs explicitly if you are using the lower-level API:

```python
session.add_all(outputs)
session.commit()
```

When you execute through `MutationWorkspace`, `workspace.save(session)` adds the
known execution outputs for you.

## Safety

Timeouts stop long-running subprocesses, but the virtual environment is not a
security sandbox. Do not prepare or execute untrusted projects, dependencies,
or serialized inputs.

