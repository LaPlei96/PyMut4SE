# ORM models

PyMut4SE uses SQLAlchemy 2.x declarative models. Import the shared metadata and
all public model classes from `pymut4se.model`:

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

## Object graph

`Project` is the persistence root. Its collections contain every entity found by
project exploration:

```text
Project
├── requirements ── Requirement
├── packages ── Package.children / Package.modules
├── modules ─── Module.code_chunks
├── code_chunks ── CodeChunk.parent / CodeChunk.children
│                  CodeChunk.original / CodeChunk.derived_chunks
│                  CodeChunk.inputs
│                  CodeChunk.execution_outputs
│                  CodeChunk.test_execution_outputs
├── test_suites ── TestSuite.children / TestSuite.test_cases
└── test_cases ── TestCase.targets ── TestTarget.module / TestTarget.chunk
```

Foreign-key attributes such as `module_id` remain available because SQLAlchemy
uses them for storage, but application code should normally navigate through the
corresponding relationship (`chunk.module`, `module.package`, and so on).

## Creating and persisting a graph

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.model import (
    Base,
    CodeChunk,
    ExecutionOutput,
    FunctionInput,
    Module,
    Package,
    Project,
)

package = Package(name="demo", path="demo")
module = Module(name="demo.math", path="demo/math.py", package_id=package.package_id)
chunk = CodeChunk(
    code="def add(left, right): return left + right",
    module_id=module.module_id,
    function_name="add",
    chunk_type="function",
    start_line=1,
    end_line=1,
)

package.modules.append(module)
module.code_chunks.append(chunk)
function_input = FunctionInput.from_value(
    (1, 2),
    "add(1, 2)",
    original_chunk=chunk,
)
ExecutionOutput(
    success=True,
    output={"result": 3},
    code_chunk=chunk,
    function_input=function_input,
    environment_id="prepared-environment-id",
    time_taken=0.01,
)
project = Project(
    name="demo",
    path=".",
    requirements_path="requirements.txt",
    requirements_content="sqlalchemy>=2\npytest\n",
    requirements=["sqlalchemy>=2", "pytest"],
    packages=[package],
    modules=[module],
    code_chunks=[chunk],
)

engine = create_engine("sqlite:///pymut4se.db")
Base.metadata.create_all(engine)
with Session(engine) as session:
    session.add(project)
    session.commit()
```

SQLAlchemy's default `save-update` cascade persists the objects reachable from
`project`; each entity does not need to be added separately.

## Model reference

### `Project`

Stores project paths and parsed requirements. `packages`, `modules`,
`code_chunks`, `test_suites`, and `test_cases` are ORM collections. The
`*_count` properties report their current sizes. `requirements_path` and
`requirements_content` preserve the discovered installation manifest.
`requirements` contains normalized `Requirement` rows, while
`get_requirement_strings()` returns their specifications as a plain list for
installer fallback.

### `Requirement`

Stores one dependency specification such as `sqlalchemy>=2`. Requirements belong
to a project through `Requirement.project`; their `position` preserves discovery
order. A project cannot contain duplicate specifications.

### `Package`

Represents a directory containing `__init__.py`. `parent` and `children` form a
self-referential package tree; `modules` contains modules directly assigned to
the package. Top-level packages have no parent.

### `Module`

Stores the module's qualified name, relative path, and source. `code_chunks`
contains originals and mutants. `original_code_chunks` is a read-only filtered
relationship for chunks whose `mutation_degree` is zero.

### `CodeChunk`

Stores source code, inclusive one-based line boundaries, and mutation metadata.
`function_name` is the chunk's sole domain name and participates in its stable
identity. Mutants reference their immediate predecessor through `parent`; the
reverse collection is `children`. They also reference the degree-zero ancestor
directly through `original`, whose reverse collection is `derived_chunks`.
Degree-zero chunks have `original=None`.

`inputs` contains predetermined `FunctionInput` records owned by a degree-zero
chunk. `applicable_inputs` returns that same collection on the original and on
every mutant that links to it.

### `FunctionInput`

Stores reusable input for a function-sized chunk. Serialized inputs encode a
tuple of positional arguments:

```python
function_input = FunctionInput.from_value(
    (10, 20),
    "add(10, 20)",
    original_chunk=chunk,
)

assert function_input.deserialize_value() == (10, 20)
assert chunk.applicable_inputs == [function_input]
```

Text inputs can instead be created with
`FunctionInput.from_text_representation(...)`. `target_chunks` returns the
degree-zero owner followed by all its mutants; each mutant exposes the same input
through `applicable_inputs`. Inputs must be treated as trusted data because
serialized values use Python pickle.

### `ExecutionOutput`

Stores the result of running one specific original or mutant chunk with an
applicable `FunctionInput`. Construct it with the related objects; their IDs are
derived internally:

```python
execution = ExecutionOutput(
    success=True,
    output={"result": 30},
    code_chunk=mutant,
    function_input=function_input,
    environment_id=environment.environment_id,
    time_taken=0.02,
)
```

`output` must be JSON-serializable and `time_taken` cannot be negative. Reverse
navigation is available through `chunk.execution_outputs` and
`function_input.execution_outputs`. Identical execution content produces the same
content-addressed ID. A unique constraint permits only one result for each
chunk, input, and prepared environment combination.

### `TestSuite`

Represents either a test directory or test module; `suite_type` must be
`"directory"` or `"module"`. Suites form a hierarchy through `parent` and
`children`. Module suites contain `test_cases` and may have an inferred
`target_module`.

### `TestCase`

Represents a discovered test function or method. `targets` contains the persisted
evidence-backed associations. Convenience properties expose `target_chunk`,
`target_chunks`, `target_module`, and `target_modules`, ordered by confidence and
deduplicated by entity ID.

`execution_outputs` contains persisted results from running the case against
related original or mutant chunks.

### `TestExecutionOutput`

Stores one pytest result for a code chunk, related test case, and prepared
environment. It records success, pytest's return code, captured output, errors,
and elapsed time. Reverse navigation is available through
`chunk.test_execution_outputs` and `test_case.execution_outputs`; a unique
constraint allows only one result for each chunk, test, and environment.

### `TestTarget`

Connects a test case to a module, code chunk, or both. Every association records
an `evidence` category, confidence from `0.0` to `1.0`, and an optional source
line. Supported evidence values are `direct_call`, `qualified_call`, `import`,
`name_match`, `coverage`, and `manual`.

Navigation is bidirectional: `Module.test_targets` and `CodeChunk.test_targets`
answer which tests are connected to a production entity, while each target's
`test_case` points back to the originating test.

Manual associations can be created explicitly:

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

## Querying tests and production targets

The association graph supports navigation in both directions. Relationship access
may issue lazy-loading queries, so use it while the objects are attached to an
open `Session`.

### Code chunk to test cases

For an already loaded chunk, follow its target associations and deduplicate test
cases by ID:

```python
test_cases = list({
    target.test_case.test_id: target.test_case
    for target in chunk.test_targets
}.values())
```

To retrieve them directly from the database:

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

### Test case to code chunks

Use the confidence-ordered convenience collection:

```python
code_chunks = test_case.target_chunks
primary_chunk = test_case.target_chunk
```

The complete evidence is available through `test_case.targets`:

```python
for target in test_case.targets:
    if target.chunk is not None:
        print(target.chunk.function_name, target.evidence, target.confidence, target.source_line)
```

A database query for all chunks targeted by a case is:

```python
statement = (
    select(CodeChunk)
    .join(TestTarget, TestTarget.chunk_id == CodeChunk.chunk_id)
    .where(TestTarget.test_id == test_case.test_id)
    .distinct()
)
code_chunks = session.scalars(statement).all()
```

### Module to test cases

Every chunk target created by exploration also records its owning module. This
makes module-level lookup independent of whether the precise chunk was resolved:

```python
test_cases = list({
    target.test_case.test_id: target.test_case
    for target in module.test_targets
}.values())
```

Or query the database:

```python
statement = (
    select(TestCase)
    .join(TestCase.targets)
    .where(TestTarget.module_id == module.module_id)
    .distinct()
)
test_cases = session.scalars(statement).all()
```

### Test case to modules

The convenience properties include modules inferred directly and modules implied
by chunk targets:

```python
modules = test_case.target_modules
primary_module = test_case.target_module
```

### Test suite to modules

`TestSuite.target_module` is the suite-level module inferred from the test file's
name and imports. Individual cases can provide additional or more precise module
links. Combine both sources to retrieve every module applying to a suite:

```python
modules_by_id = {}

if test_suite.target_module is not None:
    modules_by_id[test_suite.target_module.module_id] = test_suite.target_module

for test_case in test_suite.test_cases:
    for module in test_case.target_modules:
        modules_by_id[module.module_id] = module

modules = list(modules_by_id.values())
```

To retrieve case-level module targets from the database:

```python
statement = (
    select(Module)
    .join(TestTarget, TestTarget.module_id == Module.module_id)
    .join(TestCase, TestCase.test_id == TestTarget.test_id)
    .where(TestCase.suite_id == test_suite.suite_id)
    .distinct()
)
modules = session.scalars(statement).all()

if test_suite.target_module is not None and test_suite.target_module not in modules:
    modules.insert(0, test_suite.target_module)
```

### Module to test suites

A module may be connected directly to a suite and indirectly through its test
cases. Combine both kinds of evidence:

```python
from pymut4se.model import TestSuite

direct_statement = select(TestSuite).where(TestSuite.target_module_id == module.module_id)
direct_suites = session.scalars(direct_statement).all()

case_statement = (
    select(TestSuite)
    .join(TestCase, TestCase.suite_id == TestSuite.suite_id)
    .join(TestTarget, TestTarget.test_id == TestCase.test_id)
    .where(TestTarget.module_id == module.module_id)
    .distinct()
)
case_suites = session.scalars(case_statement).all()

suites = list({
    suite.suite_id: suite
    for suite in (*direct_suites, *case_suites)
}.values())
```

When fetching many entities, use `selectinload` for the relevant relationships to
avoid one lazy-loading query per test case or target.

## Stable identifiers

IDs are SHA-256 hashes generated immediately when objects are constructed. Their
identity inputs intentionally remain stable:

| Object | Identity input |
| --- | --- |
| Project | `name:path:absolute_path` |
| Package | `parent_id:name:path` |
| Module | `package_id:name:path` |
| CodeChunk | `module_id:function_name:chunk_type:start_line:end_line:code` |
| FunctionInput | `original_chunk_id:type:value` |
| ExecutionOutput | `code_chunk_id:input_id:environment_id:success:output:error_message:time_taken` |
| Requirement | `project_id:specification` |
| TestSuite | `parent_id:name:path:suite_type` |
| TestCase | `suite_id:name:start_line` |
| TestExecutionOutput | `code_chunk_id:test_id:environment_id:success:output:error_message:return_code:time_taken` |
| TestTarget | `test_id:module_id:chunk_id:evidence:source_line` |

An explicit primary-key value can be passed when importing existing data.
