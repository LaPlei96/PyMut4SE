# Mutation Generation

Most users generate mutants through the high-level workspace:

```python
mutants = workspace.mutate_chunks_with_tests(workspace.chunks, "all")
```

This page describes the lower-level mutation API for custom workflows,
operator development, and rendering complete mutated modules.

## Generate Mutants Directly

```python
from pymut4se.mutation import generate_mutants
from pymut4se.mutation.generic import ArithmeticMutation, RelationalMutation

mutants = generate_mutants(
    target=module,
    mutation_operators=[ArithmeticMutation, RelationalMutation],
    max_degree=1,
)
```

Targets can be:

| Target | Behavior |
| --- | --- |
| `CodeChunk` | Mutate that chunk's degree-zero original. |
| `Module` | Mutate all degree-zero chunks in the module. |
| `Package` | Mutate chunks in the package, child packages, and their modules. |

Operator classes and operator instances are both accepted.

## Higher-Order Mutants

`max_degree=1` creates first-order mutants. Larger values continue mutating the
new chain:

```python
mutants = generate_mutants(module, [ArithmeticMutation], max_degree=2)
```

Higher-order generation can grow quickly. PyMut4SE deduplicates normalized AST
states so inverse operators do not recreate the same program under different
formatting.

## Generated Relationships

Each generated mutant is a `CodeChunk` connected to the existing graph:

| Relationship | Meaning |
| --- | --- |
| `mutant.parent` | The chunk this mutant was generated from. |
| `mutant.children` | Later mutants generated from this mutant. |
| `mutant.original` | The degree-zero source chunk. |
| `mutant.module` | The same module as the original. |
| `mutant.project` | The same project, when available. |

Degree-zero chunks have `original=None`.

When the project was already persisted, add newly generated mutants before
committing:

```python
with Session(engine) as session:
    project = session.get(Project, project_id)
    module = project.modules[0]

    mutants = generate_mutants(module, [ArithmeticMutation], max_degree=1)

    session.add_all(mutants)
    session.commit()
```

Keep persisted targets attached to an open session while generating mutants, or
preload the package, module, and chunk relationships you need.

## Build Complete Mutated Source

`build_mutant()` renders the full module source for one original or mutant
chunk:

```python
from pymut4se.mutation import build_mutant

module_source = build_mutant(mutant)
```

It returns a string and does not modify `Module.source`.

For higher-order mutants, replacement boundaries come from the degree-zero
ancestor. This keeps code after the original function intact when mutations add
or remove lines.

`build_mutant()` also restores method indentation and preserves the module's
newline style.

## Implement An Operator

Operators implement the `Mutation` interface. AST-based operators usually
inherit from `PythonASTMutation`, which handles parsing dedented function and
method chunks.

Use `build_mutated_code_chunk()` to create correctly linked mutants:

```python
from pymut4se.mutation import build_mutated_code_chunk

return build_mutated_code_chunk(
    original=chunk,
    mutated_code=new_source,
    relative_line_changed=node.lineno,
    relative_column_changed=node.col_offset,
    mutation_type="conditional",
    mutation_operator=type(self).__name__,
)
```

The helper:

- increments the mutation degree;
- links the immediate parent and degree-zero original;
- connects the mutant to the surrounding module and project;
- converts relative line and column positions to project source locations.

See [Generic mutation operators](operators.md) for the implemented operator set
and expected metadata.

