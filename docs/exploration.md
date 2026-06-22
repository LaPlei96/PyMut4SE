# Project exploration

The exploration package parses Python source with `ast` and returns a connected
SQLAlchemy object graph. It does not write to a database by itself.

## Python API

```python
from pymut4se.exploration import explore_path

result = explore_path("src")
project = result.project

print(project.module_count)
for module in project.modules:
    print(module.name, len(module.code_chunks))
```

`ExplorationResult` also exposes `packages`, `modules`, `code_chunks`,
`test_suites`, and `test_cases`. These lists contain the same object instances as
the corresponding `Project` relationships.

To persist the complete result:

```python
with Session(engine) as session:
    session.add(result.project)
    session.commit()
```

## Accepted paths

- A Python file explores that single standalone module.
- A source directory explores Python files recursively.
- A project root explores its source and tests recursively.
- A directory named `src` also searches its parent for sibling `test/` and
  `tests/` directories and root-level `test_*.py` or `*_test.py` files.

Directory traversal prunes virtual environments, caches, VCS metadata,
third-party JavaScript packages, and build output. The exclusions include
`.venv`, `venv`, `env`, `__pycache__`, `.pytest_cache`, `.mypy_cache`,
`.ruff_cache`, `.tox`, `.nox`, `.git`, `node_modules`, `build`, and `dist`.

## Discovery behavior

Packages are directories containing `__init__.py`. Package and suite hierarchies
are represented with self-referential SQLAlchemy relationships.

Production modules exclude test paths and `__init__.py`. Function chunks are
created for synchronous functions, asynchronous functions, methods, and nested
functions. Their names retain qualification, such as
`Service.execute.normalize`. When a function is decorated, its chunk starts at
the first decorator so mutations can preserve, replace, or remove decorators
while rebuilding the complete module.

Test files follow common conventions: a `test` or `tests` directory, a
`test_*.py` filename, or a `*_test.py` filename. Test target inference uses
imports, called names, aliases, test names, and module names. Each inferred link
is stored as a `TestTarget` with its evidence, confidence, and call line:

| Evidence | Typical confidence | Meaning |
| --- | ---: | --- |
| `direct_call` | `0.98` | A directly imported function is called. |
| `qualified_call` | `0.95` | A function is called through a module or import alias. |
| `import` | `0.65` | A module is resolved but no precise chunk is identified. |
| `name_match` | `0.40` | Only the test/function naming convention matches. |
| `manual` | user supplied | A caller explicitly confirms a target. |
| `coverage` | collector supplied | Runtime execution confirms a target. |

The current explorer emits the first four categories. `manual` is available to
callers and `coverage` is reserved for runtime integration. Inference remains
heuristic: unresolved tests are valid and simply have no target associations.

See [Querying tests and production targets](models.md#querying-tests-and-production-targets)
for relationship navigation and SQLAlchemy queries in both directions between
test cases, test suites, modules, and code chunks.

The nearest `requirements.txt` or `pyproject.toml` is searched for by walking up
from the explored path. Its path and raw content are preserved on the `Project`.
Standard, optional, and PEP 735-style dependencies are flattened, deduplicated,
and stored as related `Requirement` rows. Use
`project.get_requirement_strings()` when an installer needs a plain string list
because the original manifest is unavailable.

## Command line

Run exploration without persistence and print a summary:

```bash
python -m pymut4se.exploration src
```

The command reports the project ID and entity counts. Use the Python API when the
graph should be inspected further or stored in a database.

## Errors

- A missing path raises `FileNotFoundError`.
- A single input file without a `.py` suffix raises `ValueError`.
- Invalid Python syntax raises `SyntaxError` with the discovered file as context.
