# Getting Started

This guide gets you from a Python project to generated mutants, related pytest
execution, a mutation score, and persisted results.

Most users should start with the high-level API. It keeps the discovered
SQLAlchemy objects available, but handles the usual coordination work for
exploration, mutation, execution, caching, and saving.

## 1. Install

PyMut4SE requires Python 3.13 or newer. From this repository:

```bash
uv sync
```

The target project can have its own dependencies. PyMut4SE installs those into
a reusable environment for that project when tests or inputs are executed.

## 2. Discover A Project

Pass a Python file, a `src` directory, or a project root:

```python
from pymut4se.api import discover

workspace = discover("path/to/target-project")

print(workspace)
print(workspace.statistics())
```

Discovery finds packages, modules, function-sized code chunks, common
dependency manifests, and pytest cases. It also infers which tests appear to
exercise each code chunk.

Useful first checks:

```python
workspace.packages
workspace.modules
workspace.chunks

workspace.find_modules("core")
workspace.find_chunks("normalize")
```

If you explored a `src` directory, PyMut4SE also checks sibling `test/` and
`tests/` directories in the parent project.

## 3. Choose What To Mutate

You can mutate packages, modules, or individual chunks. Start small:

```python
chunks = workspace.find_chunks("function_to_mutate")

mutants = workspace.mutate(
    chunks,
    operators=["arithmetic", "relational", "logical-connector"],
    max_degree=1,
)

print(workspace.mutant_statistics())
```

A single operator name also works:

```python
mutants = workspace.mutate(chunks, "arithmetic")
```

Use `"all"` when you want the full implemented operator catalogue:

```python
mutants = workspace.mutate(chunks, "all", max_degree=1)
```

Higher values of `max_degree` generate higher-order mutants, but the search
space can grow quickly. Begin with `max_degree=1` and a focused target.

## 4. Mutate Only Tested Code

For normal mutation testing, you often want to skip chunks with no inferred
tests:

```python
tested_chunks = workspace.chunks_with_tests()

mutants = workspace.mutate_chunks_with_tests(
    tested_chunks,
    operators=["arithmetic", "relational"],
)
```

You can inspect the related tests before executing anything:

```python
for chunk in tested_chunks:
    print(chunk.function_name)
    for test_case in workspace.tests_for(chunk):
        print("  ", test_case.name)
```

Test targeting is heuristic. If a project uses dynamic imports, fixtures, or
indirect calls, review these links before treating the score as final.

## 5. Run Related Tests

The workspace prepares and reuses the target project environment automatically:

```python
outputs = workspace.run_tests_for_chunks_with_tests(
    mutants,
    parallel=True,
    max_workers=4,
    timeout_seconds=20,
)
```

`run_tests_for_chunks_with_tests()` only runs chunks with inferred related tests
and never falls back to the full test suite.

If you want PyMut4SE to run the full discovered test suite when a chunk has no
related tests, use `run_tests()` with fallback enabled:

```python
outputs = workspace.run_tests(
    mutants,
    fallback_to_full_suite=True,
)
```

Execution installs dependencies and runs arbitrary target project code. Only
use projects you trust.

## 6. Check The Mutation Score

After test execution:

```python
score = workspace.mutation_score(mutants)

print(score)
print(score.as_dict())
```

The score is calculated as:

```text
killed / (killed + survived)
```

Untested, incomplete, and infrastructure-error mutants are reported separately
and excluded from the denominator.

## 7. Save Results

The high-level API does not create or own your database. Give it a SQLAlchemy
session when you want to persist the accumulated graph:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.model import Base

engine = create_engine("sqlite:///pymut4se.db")
Base.metadata.create_all(engine)

with Session(engine) as session:
    workspace.save(session, commit=True)
```

If you plan to keep using the same `workspace`, `chunk`, or `mutant` variables
after committing, create sessions with `expire_on_commit=False`:

```python
from sqlalchemy.orm import sessionmaker

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

with SessionLocal() as session:
    workspace.save(session)
    session.commit()
```

Otherwise, the simplest pattern is to save at the end of the workflow.

## Common Recipes

Run the shortest useful mutation-testing flow:

```python
from pymut4se.api import discover

workspace = discover("path/to/target-project")
mutants = workspace.mutate_chunks_with_tests(workspace.chunks, "all")
workspace.run_tests_for_chunks_with_tests(mutants, max_workers=4)
print(workspace.mutation_score(mutants))
```

Focus on one module:

```python
module = workspace.find_modules("calculator.core")[0]
mutants = workspace.mutate_chunks_with_tests(module, ["arithmetic", "relational"])
workspace.run_tests_for_chunks_with_tests(mutants)
```

Run quietly inside another tool:

```python
mutants = workspace.mutate_chunks_with_tests(
    workspace.chunks,
    "all",
    show_progress=False,
)
outputs = workspace.run_tests_for_chunks_with_tests(
    mutants,
    show_progress=False,
)
```

## Where To Go Next

- [High-level API](api.md): workspace methods, search helpers, execution, score,
  and persistence.
- [Operators](operators.md): every implemented mutation operator.
- [Exploration](exploration.md): path handling and test inference.
- [Execution](execution.md): environments, subprocess behavior, caching, and
  parallelism.
- [Models](models.md): SQLAlchemy relationships and persistence details.
- [Mutation generation](mutation.md): lower-level generation and custom
  operators.

