# Project Exploration

Exploration turns Python source into a connected SQLAlchemy object graph. It
does not write anything to a database by itself.

Use the high-level API for normal workflows:

```python
from pymut4se.api import discover

workspace = discover("path/to/project")
print(workspace.statistics())
```

Use the lower-level exploration API when you want direct access to the raw
`ExplorationResult`:

```python
from pymut4se.exploration import explore_path

result = explore_path("path/to/project")

print(result.project.name)
print(len(result.modules))
print(len(result.code_chunks))
print(len(result.test_cases))
```

## What Gets Discovered

Exploration finds:

- packages, modules, and function-sized code chunks;
- synchronous functions, asynchronous functions, methods, and nested functions;
- pytest suites and test functions;
- likely links from tests to production modules and chunks;
- dependency manifests such as `requirements.txt` and `pyproject.toml`.

`ExplorationResult` exposes the same object instances through convenient lists:

```python
result.project
result.packages
result.modules
result.code_chunks
result.test_suites
result.test_cases
```

## Accepted Paths

You can explore:

| Input | Behavior |
| --- | --- |
| Python file | Explore one standalone module. |
| Source directory | Explore Python files recursively. |
| Project root | Explore source and tests recursively. |
| Directory named `src` | Also check the parent for sibling `test/` and `tests/` directories. |

Traversal skips common generated or third-party directories, including `.venv`,
`venv`, `env`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`,
`.tox`, `.nox`, `.git`, `node_modules`, `build`, and `dist`.

## Source Chunks

Production modules exclude test paths and `__init__.py`. Function chunks keep
qualified names, for example:

```text
Service.execute.normalize
```

When a function has decorators, the chunk starts at the first decorator. That
lets mutation and module rebuilding preserve, replace, or remove decorators
correctly.

## Test Discovery

Test files follow common pytest conventions:

- files in a `test` or `tests` directory;
- files named `test_*.py`;
- files named `*_test.py`.

Test target inference uses imports, aliases, calls, test names, and module
names. The result is a set of `TestTarget` records with evidence and confidence.

| Evidence | Meaning |
| --- | --- |
| `direct_call` | A directly imported function is called. |
| `qualified_call` | A function is called through a module or import alias. |
| `import` | A module is resolved, but no precise chunk is identified. |
| `name_match` | The test/function naming convention matches. |
| `manual` | A caller explicitly created the association. |
| `coverage` | Reserved for runtime coverage integration. |

The current explorer emits `direct_call`, `qualified_call`, `import`, and
`name_match`. Inference is deliberately heuristic. A test with no inferred
targets is still valid; it simply has no `TestTarget` rows.

To inspect inferred links:

```python
for chunk in result.code_chunks:
    tests = chunk.related_test_cases
    if tests:
        print(chunk.function_name, [test.name for test in tests])
```

## Requirements

Exploration searches upward from the explored path for the nearest
`requirements.txt` or `pyproject.toml`. It stores:

- the manifest path;
- the raw manifest content;
- normalized dependency strings as `Requirement` rows.

Use this when an installer needs plain strings:

```python
requirements = result.project.get_requirement_strings()
```

## Persisting The Result

Add the project root to a SQLAlchemy session. The related graph is reachable
from it:

```python
from sqlalchemy.orm import Session

with Session(engine) as session:
    session.add(result.project)
    session.commit()
```

For most workflows, `workspace.save(session)` from the high-level API is more
convenient because it also includes generated mutants and execution results.

## Command Line

Print an exploration summary without persistence:

```bash
python -m pymut4se.exploration path/to/project
```

Use the Python API when you want to inspect or save the graph.

## Errors

- Missing paths raise `FileNotFoundError`.
- A single input file without a `.py` suffix raises `ValueError`.
- Invalid Python syntax raises `SyntaxError` with the file path as context.

