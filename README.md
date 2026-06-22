# PyMut4SE

PyMut4SE explores Python projects into a SQLAlchemy object graph, generates
first- and higher-order function mutants, and executes those chunks against
predetermined inputs or their related pytest cases.

The project is under active development. The current API supports:

- exploration from a Python file, `src` directory, or project root;
- persisted projects, dependencies, source structure, tests, mutants, inputs,
  and execution results;
- AST-based generic mutation operators;
- reusable project virtual environments;
- cached function and pytest execution; and
- bounded parallel pytest execution across multiple chunks.

## Installation

PyMut4SE requires Python 3.13 or newer. With [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync
```

Run the checks with:

```bash
uv run pytest
uv run ruff check .
uv run ty check
```

## Start here

The [getting-started guide](docs/getting-started.md) walks through the complete
flow: explore and persist a project, choose a code chunk, generate mutants,
prepare its virtual environment, execute inputs and related tests, and save the
results.

Reference documentation:

- [Project exploration](docs/exploration.md)
- [ORM models and relationships](docs/models.md)
- [Mutation generation](docs/mutation.md)
- [Generic mutation operators](docs/operators.md)
- [Execution and reusable environments](docs/execution.md)

## Safety and current limitations

Explored projects and serialized inputs are trusted code. Their dependencies
are installed and their modules and tests execute as local subprocesses; the
virtual environment and timeout controls are not a security sandbox.

Test-to-code associations are inferred statically and may need manual
correction for dynamic imports or indirect calls. Mutation counts can also grow
quickly at higher degrees, so begin with `max_degree=1` and a focused chunk.
