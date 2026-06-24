# Getting started

This guide follows one project from source discovery to persisted mutation and
execution results. It uses SQLite for storage, but the models work with any
SQLAlchemy-supported database.

For the shortest route through this workflow, use the
[high-level API](api.md):

```python
from pymut4se.api import discover

workspace = discover("path/to/target-project")
print(workspace.statistics())

chunks = workspace.find_chunks("function_to_mutate")
mutants = workspace.mutate(
    chunks,
    operators=["arithmetic", "relational", "logical-connector"],
)
print(workspace.mutant_statistics())

workspace.run_tests(mutants, parallel=True, max_workers=4)
```

The remaining sections show the underlying exploration, model, mutation, and
execution APIs for users who need direct transaction and object-graph control.

## 1. Install PyMut4SE

PyMut4SE requires Python 3.13 or newer. From this repository:

```bash
uv sync
```

The project being mutated can have its own dependencies. PyMut4SE installs
those later into a reusable virtual environment; they do not need to be added
to PyMut4SE itself.

## 2. Explore and persist a project

Pass a Python file, a `src` directory, or a project root to `explore_path`:

```python
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.exploration import explore_path
from pymut4se.model import Base

project_path = Path("path/to/target-project").resolve()
result = explore_path(project_path)

engine = create_engine("sqlite:///pymut4se.db")
Base.metadata.create_all(engine)

session = Session(engine)
session.add(result.project)
session.commit()

print(f"modules: {result.project.module_count}")
print(f"original chunks: {len(result.code_chunks)}")
print(f"tests: {result.project.test_case_count}")
print(f"requirements: {result.project.get_requirement_strings()}")
```

Exploration builds one connected ORM graph. It discovers functions and methods
as degree-zero `CodeChunk` objects, finds common dependency manifests, and
infers links from pytest cases to production modules and chunks. Virtual
environments, caches, version-control metadata, and build output are skipped.

When exploring `src`, PyMut4SE also checks the parent project for sibling
`test/` and `tests/` directories. Test targeting is heuristic, so inspect
`chunk.related_test_cases` before relying on it for mutation verdicts.

## 3. Select a chunk and its operators

Choose a degree-zero chunk, then generate first-order mutants with a focused
operator set:

```python
from pymut4se.mutation import generate_mutants
from pymut4se.mutation.generic import (
    ArithmeticMutation,
    LogicalConnectorMutation,
    RelationalMutation,
    UnaryMutation,
)

original = next(
    chunk
    for chunk in result.code_chunks
    if chunk.function_name == "function_to_mutate"
)

mutants = generate_mutants(
    target=original,
    mutation_operators=[
        ArithmeticMutation,
        LogicalConnectorMutation,
        RelationalMutation,
        UnaryMutation,
    ],
    max_degree=1,
)
session.add_all(mutants)

print(f"generated {len(mutants)} mutants")
for mutant in mutants:
    print(mutant.mutation_operator, mutant.line_changed)
```

Operator classes and instances are both accepted. Change `max_degree` to `2`
or more for higher-order mutants, but expect the search space to grow quickly.
Each mutant is attached to the same project and module, its immediate `parent`,
and its degree-zero `original` ancestor.

See the [operator catalogue](operators.md) before choosing a broader set. To
preview the complete mutated module without writing it to disk:

```python
from pymut4se.mutation import build_mutant

module_source = build_mutant(mutants[0])
print(module_source)
```

## 4. Optionally add predetermined inputs

Function inputs belong to the original chunk and automatically apply to all of
its mutants. A text input can be JSON, a Python literal collection, or a call
expression containing literal arguments:

```python
from pymut4se.model import FunctionInput

function_input = FunctionInput.from_text_representation(
    "function_to_mutate(3, 5)",
    original_chunk=original,
)
session.add(function_input)
```

For trusted Python values that are awkward to express as text, use the
serialized form:

```python
function_input = FunctionInput.from_value(
    (3, 5),
    "function_to_mutate(3, 5)",
    original_chunk=original,
)
session.add(function_input)
```

Serialized values use `pickle`; never load serialized inputs from an untrusted
source. Skip this step when related pytest cases are the only execution oracle.

## 5. Prepare the reusable environment

Create one virtual environment for the explored project:

```python
from pymut4se.execution import PythonExecutionEnvironment

environment = PythonExecutionEnvironment.for_project(result.project)
environment.prepare()
```

The default location is `.pymut4se/venvs/<project_id>` under the explored path.
Preparation installs the preserved `requirements.txt`, or falls back to the
normalized requirements stored on the project. It also installs pytest as the
test runner. A dependency fingerprint prevents unchanged requirements from
being installed again.

Preparing an environment installs and later executes arbitrary project code.
Only use projects you trust.

## 6. Execute inputs and related tests

The standalone executor substitutes a chunk into a temporary copy of its full
module and runs it with the prepared environment:

```python
from pymut4se.execution import StandalonePythonExecution

executor = StandalonePythonExecution(timeout_seconds=5)

original_input_outputs = executor.execute_all(original, environment)
mutant_input_outputs = [
    output
    for mutant in mutants
    for output in executor.execute_all(mutant, environment)
]

original_test_outputs = executor.execute_related_tests(original, environment)
mutant_test_outputs = [
    output
    for mutant in mutants
    for output in executor.execute_related_tests(mutant, environment)
]
```

`execute_all` uses every input applicable to the chunk. If there are no inputs,
it returns an empty list. `execute_related_tests` behaves the same way when no
test association was discovered.

Both methods reuse one module build per call. They also return an existing ORM
output instead of rerunning the same chunk/input/environment or
chunk/test/environment combination.

## 7. Run many mutant test sets in parallel

For several mutants, parallel execution avoids serially waiting on independent
pytest subprocesses:

```python
from pymut4se.execution import ParallelExecution

parallel = ParallelExecution(max_workers=4, timeout_seconds=5)
mutant_test_outputs = parallel.execute_related_tests(mutants, environment)
```

Each worker receives an isolated project copy while sharing the prepared venv
read-only. ORM access and output construction remain on the calling thread, so
do not pass SQLAlchemy sessions into workers. Tune `max_workers` to the target
tests' CPU and memory cost rather than automatically using every core.

## 8. Persist the generated and executed graph

Add outputs explicitly, then commit the project graph and results:

```python
all_outputs = [
    *original_input_outputs,
    *mutant_input_outputs,
    *original_test_outputs,
    *mutant_test_outputs,
]

session.add_all(all_outputs)
session.commit()
session.close()
```

In a long-running application, keep ORM objects attached to one open session
while traversing lazy relationships, generating mutants, and resolving cached
outputs. When reopening a stored project in a later process, load the required
module, chunk, input, and test relationships before detaching it.

The result graph can now be navigated directly:

```python
for mutant in original.derived_chunks:
    input_results = mutant.execution_outputs
    test_results = mutant.test_execution_outputs
    killed_by = [result.test_case.name for result in test_results if not result.success]
    print(mutant.chunk_id, len(input_results), killed_by)
```

A failed related test is evidence that the mutant differs observably from the
tested original, but PyMut4SE currently stores raw outcomes rather than a final
mutation score or report.

## Where to go next

- [Exploration](exploration.md) explains path handling and test inference.
- [Models](models.md) documents relationships and SQLAlchemy queries.
- [Mutation generation](mutation.md) covers higher-order generation and custom
  operators.
- [Operators](operators.md) lists every implemented mutation operator.
- [Execution](execution.md) details caching, environments, subprocess behavior,
  and parallelism.
