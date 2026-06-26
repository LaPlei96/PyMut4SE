# High-Level API

The `pymut4se.api` package is the easiest way to use PyMut4SE. It gives you a
`MutationWorkspace` that keeps the discovered ORM objects available while
handling the common workflow:

```text
discover -> select chunks -> mutate -> execute tests -> score -> save
```

Start here when you want a productive mutation-testing workflow. Drop down to
the lower-level exploration, mutation, execution, and model APIs only when you
need custom transaction handling or custom operators.

## Quick Start

```python
from pymut4se.api import discover

workspace = discover("path/to/project")

mutants = workspace.mutate_chunks_with_tests(
    workspace.chunks,
    operators=["arithmetic", "relational"],
)

workspace.run_tests_for_chunks_with_tests(mutants, max_workers=4)

score = workspace.mutation_score(mutants)
print(score)
```

This flow only mutates chunks that have inferred related tests, runs those
related tests, and reports a mutation score.

## Common Recipes

Discover and inspect a project:

```python
workspace = discover("path/to/project")

print(workspace)
print(workspace.statistics())

workspace.packages
workspace.modules
workspace.chunks
```

Find targets by substring or glob:

```python
workspace.find_packages("calculator")
workspace.find_modules("*core*")
workspace.find_chunks("normalize")
workspace.find_chunks("calculator.core:add")
```

Mutate one target:

```python
chunk = workspace.find_chunks("normalize")[0]
mutants = workspace.mutate(chunk, "arithmetic")
```

Mutate only code with inferred tests:

```python
tested_chunks = workspace.chunks_with_tests()
mutants = workspace.mutate_chunks_with_tests(tested_chunks, "all")
```

Run related tests for generated mutants:

```python
outputs = workspace.run_tests_for_chunks_with_tests(
    mutants,
    parallel=True,
    max_workers=4,
    timeout_seconds=20,
)
```

Run the full discovered test suite when no related tests were inferred:

```python
outputs = workspace.run_tests(
    mutants,
    fallback_to_full_suite=True,
)
```

Persist everything:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.model import Base

engine = create_engine("sqlite:///pymut4se.db")
Base.metadata.create_all(engine)

with Session(engine) as session:
    workspace.save(session, commit=True)
```

## Workspace At A Glance

Useful properties:

| Property | Meaning |
| --- | --- |
| `workspace.project` | The discovered `Project` model. |
| `workspace.packages` | Discovered packages. |
| `workspace.modules` | Discovered modules. |
| `workspace.chunks` | Original degree-zero code chunks. |
| `workspace.mutants` | Mutants generated through this workspace. |
| `workspace.inputs` | Function inputs added through this workspace. |
| `workspace.test_outputs` | Test outputs recorded through this workspace. |

Useful methods:

| Method | Purpose |
| --- | --- |
| `statistics()` | Discovery summary. |
| `operators()` | Friendly mutation operator catalogue. |
| `find_packages()` / `find_modules()` / `find_chunks()` | Search discovered objects. |
| `chunks_with_tests()` | Return chunks with inferred related tests. |
| `mutate()` | Generate mutants for selected targets. |
| `mutate_chunks_with_tests()` | Generate mutants only for tested chunks. |
| `find_mutants()` | Filter generated mutants. |
| `tests_for()` | Show inferred tests for one chunk or mutant. |
| `run_inputs()` | Execute added function inputs. |
| `run_tests()` | Execute related tests, optionally with full-suite fallback. |
| `run_tests_for_chunks_with_tests()` | Execute only chunks with inferred tests. |
| `mutation_score()` | Classify mutants from related test outcomes. |
| `save()` | Add workspace state to a caller-owned SQLAlchemy session. |

## Discover

```python
from pymut4se.api import discover

workspace = discover("path/to/project")
```

`discover()` accepts a Python file, a `src` directory, or a project root. It
discovers source structure, requirements, pytest suites, test cases, and likely
test-to-code links.

Statistics are usually the best first check:

```python
stats = workspace.statistics()
print(stats)
print(stats.as_dict())
```

The discovered entities remain normal SQLAlchemy models, so you can still use
their relationships and attributes directly when you need them.

## Search

Search helpers accept case-insensitive substrings:

```python
workspace.find_modules("optional")
workspace.find_chunks("normalize")
```

They also accept shell-style globs when the query contains `*`, `?`, or `[`:

```python
workspace.find_modules("*generic*")
workspace.find_chunks("*.service:handle_?")
```

Use `find_mutants()` after generation:

```python
workspace.find_mutants("normalize", operator="Add", degree=1)
```

Search values:

| Method | Values searched |
| --- | --- |
| `find_packages()` | Package ID, dotted name, relative path. |
| `find_modules()` | Module ID, dotted name, relative path. |
| `find_chunks()` | Chunk ID, function name, `module:function` label. |
| `find_mutants()` | Mutant ID, function name, original chunk ID. |

## Operators

List available operators:

```python
for operator in workspace.operators():
    print(operator.name, operator.description)
```

Friendly names such as `arithmetic`, `relational`, `logical-connector`, and
`delete-return` can be passed directly to `mutate()` and
`mutate_chunks_with_tests()`.

Select all implemented operators with `"all"` or `"*"`:

```python
mutants = workspace.mutate(chunks, "all", max_degree=1)
```

Operator classes and instances from `pymut4se.mutation.generic` are accepted
too.

## Mutate

Select packages, modules, or chunks:

```python
targets = [
    *workspace.find_modules("calculator.core"),
    *workspace.find_chunks("normalize"),
]

mutants = workspace.mutate(
    targets,
    operators=["arithmetic", "relational", "logical-connector"],
    max_degree=1,
)
```

Package selection includes descendant packages. If selections overlap, each
original chunk is mutated once.

Each call returns only newly generated mutants. All mutants generated through
the workspace are available in `workspace.mutants`.

For mutation testing, the more focused helper is often better:

```python
mutants = workspace.mutate_chunks_with_tests(workspace.chunks, "all")
```

`chunks_with_tests()` accepts the same target types:

```python
tested_in_module = workspace.chunks_with_tests(module)
tested_plus_mutants = workspace.chunks_with_tests(include_mutants=True)
```

Inspect generated mutants:

```python
print(workspace.mutant_statistics())

for mutant in workspace.find_mutants("normalize", degree=1):
    print(mutant.function_name, mutant.mutation_type, mutant.mutation_operator)
    print(mutant.code)
```

## Inputs And Related Tests

Inputs added to an original or mutant are stored on the degree-zero original
and apply to every derived mutant:

```python
workspace.add_input(chunk, (3, 5), label="function_name(3, 5)")
workspace.add_text_input(chunk, '{"args": [3, 5], "kwargs": {}}')
```

`add_input()` serializes trusted Python values with pickle. Use
`add_text_input()` for JSON or literal data from less trusted sources.

Review inferred tests:

```python
for test_case in workspace.tests_for(chunk):
    print(test_case.name)
```

Test inference is static and heuristic. Review related tests when dynamic
imports, fixtures, decorators, or indirect calls matter.

## Execute

The workspace prepares and reuses the target project environment automatically
on the first execution call.

Run related tests for selected chunks or mutants:

```python
outputs = workspace.run_tests(
    mutants,
    parallel=True,
    max_workers=4,
    timeout_seconds=20,
)
```

By default, `run_tests()` executes inferred related tests and does not fall
back to the full suite. Enable fallback explicitly:

```python
outputs = workspace.run_tests(mutants, fallback_to_full_suite=True)
```

Use the tested-only helper when you want to skip chunks with no inferred tests:

```python
outputs = workspace.run_tests_for_chunks_with_tests(mutants)
```

When called without explicit chunks, execution targets every mutant known to
the workspace, or all original chunks if no mutants have been generated.

Run predetermined function inputs:

```python
input_outputs = workspace.run_inputs(mutants, timeout_seconds=5)
```

Prepare the environment explicitly when needed:

```python
environment = workspace.prepare_environment(refresh_requirements=True)
```

Execution installs dependencies and runs arbitrary target project code. Only
use projects you trust.

## Progress Output

Progress is printed by default:

```text
Generating mutants: 148 new | chunks processed: 12/12
Executing inputs: 148/148 | 296 outputs
Executing tests: 148/148
```

Disable it for services, notebooks, or nested progress displays:

```python
mutants = workspace.mutate(chunks, "all", show_progress=False)
outputs = workspace.run_tests(mutants, show_progress=False)
environment = workspace.prepare_environment(show_progress=False)
```

## Mutation Score

After related test execution:

```python
score = workspace.mutation_score(mutants)

print(score)
print(score.as_dict())
```

The score is:

```text
killed / (killed + survived)
```

Classifications:

| Outcome | Meaning |
| --- | --- |
| Killed | At least one related test failed with pytest return code `1`. |
| Survived | Every related test has a successful result. |
| Untested | No applicable tests were executed. |
| Incomplete | Some tests passed, but not every related test was executed. |
| Errors | Pytest failed for collection, interruption, timeout, or infrastructure reasons. |

Untested, incomplete, and error mutants are excluded from the denominator. If
no mutant was conclusively assessed, `score.score` and `score.percentage` are
`None`.

When persisted results contain multiple environments and the workspace has no
active environment, pass the environment explicitly:

```python
score = workspace.mutation_score(mutants, environment_id="environment-id")
```

## Persist

The workspace does not create or own your database. Give it a SQLAlchemy
session:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.model import Base

engine = create_engine("sqlite:///pymut4se.db")
Base.metadata.create_all(engine)

with Session(engine) as session:
    workspace.save(session, commit=True)
```

`save()` adds the project, generated mutants, inputs, and execution outputs.
Pass `commit=False` when a larger application owns the transaction.

SQLAlchemy expires ORM objects on commit by default. After
`workspace.save(session, commit=True)`, variables you already hold, such as
`chunk`, `mutant`, or `test_case`, may need their session to lazy-load
relationships again. If the session has closed, access to relationships such as
`mutant.original`, `chunk.module`, or `chunk.related_test_cases` can raise
detached-object errors.

If you need to keep using the same workspace variables after saving, use
`expire_on_commit=False`:

```python
from sqlalchemy.orm import sessionmaker

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

with SessionLocal() as session:
    workspace.save(session)
    session.commit()
```

The simplest pattern is still to save at the end of the workflow, after
mutation, execution, and scoring have finished.

## Lower-Level APIs

The high-level API intentionally returns ORM and execution objects instead of
hiding them. Use the lower-level docs when you need more control:

- [Exploration](exploration.md): path handling and test inference.
- [Models](models.md): relationships, persistence, and SQLAlchemy queries.
- [Mutation generation](mutation.md): direct generation and custom operators.
- [Operators](operators.md): implemented mutation operators.
- [Execution](execution.md): environments, subprocesses, caching, and
  parallelism.

