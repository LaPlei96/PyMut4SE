# ORM Models

PyMut4SE stores projects, chunks, tests, mutants, inputs, and execution results
as SQLAlchemy 2.x models.

Most users do not need to construct these models by hand. The high-level API
returns them so you can inspect relationships, query persisted data, or build
custom reports.

Import public models from `pymut4se.model`:

```python
from pymut4se.model import (
    Base,
    CodeChunk,
    ExecutionOutput,
    FunctionInput,
    Module,
    Package,
    Project,
    Requirement,
    TestCase,
    TestExecutionOutput,
    TestSuite,
    TestTarget,
)
```

## Mental Model

`Project` is the root of the persisted graph.

```text
Project
|-- requirements -> Requirement
|-- packages -> Package
|-- modules -> Module -> CodeChunk
|-- code_chunks -> CodeChunk -> mutants, inputs, outputs
|-- test_suites -> TestSuite -> TestCase
`-- test_cases -> TestCase -> TestTarget -> Module / CodeChunk
```

Navigate relationships in Python when objects are attached to an open session:

```python
for module in project.modules:
    for chunk in module.original_code_chunks:
        print(module.name, chunk.function_name)
```

Foreign-key IDs such as `module_id` are available for storage and queries, but
application code is usually clearer when it follows relationships such as
`chunk.module`, `module.package`, or `test_case.targets`.

## Common Objects

### Project

The persistence root. It stores project paths, normalized requirements, and
collections for packages, modules, chunks, test suites, and test cases.

Useful helpers:

```python
project.module_count
project.code_chunk_count
project.test_case_count
project.get_requirement_strings()
```

### Package And Module

`Package` represents a directory containing `__init__.py`. Packages can have
children and modules.

`Module` stores a module's qualified name, relative path, and source. Its
`code_chunks` collection contains originals and generated mutants.
`original_code_chunks` filters that list to degree-zero chunks.

### CodeChunk

`CodeChunk` is a function-sized piece of source. Degree-zero chunks are
original source. Mutants are also `CodeChunk` objects.

Key relationships:

| Relationship | Meaning |
| --- | --- |
| `chunk.module` | The module containing the chunk. |
| `chunk.parent` | The immediate source for a mutant. |
| `chunk.children` | Mutants generated from this chunk. |
| `chunk.original` | The degree-zero ancestor for a mutant. |
| `chunk.derived_chunks` | All mutants derived from an original. |
| `chunk.inputs` | Inputs owned by an original chunk. |
| `chunk.applicable_inputs` | Inputs usable by an original or mutant. |
| `chunk.related_test_cases` | Tests inferred for an original or mutant. |

### Tests

`TestSuite` represents a test directory or test module. `TestCase` represents a
discovered test function or method.

`TestTarget` links a test case to a module, a code chunk, or both. It stores
evidence such as `direct_call`, `qualified_call`, `import`, `name_match`,
`manual`, or `coverage`.

Useful test-case shortcuts:

```python
test_case.target_chunk
test_case.target_chunks
test_case.target_module
test_case.target_modules
```

### Inputs And Outputs

`FunctionInput` stores reusable arguments for one original chunk. Those inputs
automatically apply to all mutants derived from that original:

```python
function_input = FunctionInput.from_value(
    (10, 20),
    "add(10, 20)",
    original_chunk=chunk,
)
```

`ExecutionOutput` stores one function-input execution result.
`TestExecutionOutput` stores one pytest result for one chunk, test case, and
environment.

Both output types are content-addressed and constrained so the same
chunk/input/environment or chunk/test/environment combination has only one
stored result.

## Persisting A Graph

The high-level API is the easiest path:

```python
with Session(engine) as session:
    workspace.save(session, commit=True)
```

If you are using lower-level APIs, add the project root and any newly generated
or executed objects:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.model import Base

engine = create_engine("sqlite:///pymut4se.db")
Base.metadata.create_all(engine)

with Session(engine) as session:
    session.add(project)
    session.add_all(mutants)
    session.add_all(outputs)
    session.commit()
```

SQLAlchemy relationship access may lazy-load. Keep objects attached to an open
session while traversing relationships, or load the relationships you need
before detaching objects.

## Query Recipes

### Tests For A Chunk

In memory:

```python
test_cases = chunk.related_test_cases
```

With SQLAlchemy:

```python
from sqlalchemy import select
from pymut4se.model import TestCase, TestTarget

statement = (
    select(TestCase)
    .join(TestCase.targets)
    .where(TestTarget.chunk_id == chunk.chunk_id)
    .distinct()
)

test_cases = session.scalars(statement).all()
```

### Chunks Targeted By A Test

In memory:

```python
chunks = test_case.target_chunks
primary = test_case.target_chunk
```

With SQLAlchemy:

```python
statement = (
    select(CodeChunk)
    .join(TestTarget, TestTarget.chunk_id == CodeChunk.chunk_id)
    .where(TestTarget.test_id == test_case.test_id)
    .distinct()
)

chunks = session.scalars(statement).all()
```

### Tests For A Module

```python
statement = (
    select(TestCase)
    .join(TestCase.targets)
    .where(TestTarget.module_id == module.module_id)
    .distinct()
)

test_cases = session.scalars(statement).all()
```

When fetching many related objects, use SQLAlchemy eager loading such as
`selectinload` to avoid one lazy-loading query per row.

## Manual Test Links

You can add a confirmed test-to-code association manually:

```python
target = TestTarget(
    test_id=test_case.test_id,
    module=module,
    chunk=chunk,
    evidence="manual",
    confidence=1.0,
)

test_case.targets.append(target)
```

This is useful when static inference misses dynamic imports, fixture-driven
calls, or indirect execution.

## Stable Identifiers

IDs are generated when objects are constructed. They are SHA-256 hashes of
stable identity inputs such as path, name, source range, source text, related
IDs, and execution content.

The practical consequence: recreating the same project structure, mutant, input,
or output produces the same ID. This supports caching and avoids duplicate
results for the same execution.

Explicit primary-key values can still be passed when importing existing data.

