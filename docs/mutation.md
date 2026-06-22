# Mutation generation

Mutation generation operates directly on the SQLAlchemy object graph. A target
can be a `CodeChunk`, `Module`, or `Package`; callers do not pass separate ID or
entity collections.

```python
from pymut4se.mutation import generate_mutants
from my_operators import MyMutationOperator

mutants = generate_mutants(
    target=module,
    mutation_operators=[MyMutationOperator],
    max_degree=2,
)
```

Operator instances and no-argument operator classes are both accepted. A module
target mutates its degree-zero `code_chunks`. A package target also traverses
child packages and their modules. Existing mutants are not treated as independent
sources; higher-order mutants are generated from the new chain up to
`max_degree`.

Each generated chunk is connected automatically:

- `mutant.parent` points to the chunk from which it was generated.
- `mutant.original` points directly to the degree-zero ancestor; it is `None` on
  degree-zero chunks themselves.
- `mutant.module` points to the same module.
- `mutant.project` points to the same project when available.
- Reverse collections such as `parent.children`, `module.code_chunks`, and
  `project.code_chunks` are updated by SQLAlchemy.

As a result, an already tracked project graph can persist generated mutants with
the normal session commit:

```python
with Session(engine) as session:
    project = session.get(Project, project_id)
    mutants = generate_mutants(project.modules[0], [MyMutationOperator], 2)
    session.add_all(mutants)
    session.commit()
```

When the project was already persisted, add newly generated mutants explicitly.
Relationship assignment updates the in-memory graph, but SQLAlchemy does not
automatically add a transient child merely because it was assigned from the
child side of an existing relationship.

Module and package relationships may lazy-load. Keep persistent targets attached
to an open session while generating mutants, or load the relevant package,
module, and chunk relationships beforehand.

Higher-order generation deduplicates normalized AST states rather than raw source
text. This prevents inverse operators from recreating the original program under
different `ast.unparse` formatting and keeps rejected candidates out of ORM
relationship collections.

## Building complete mutant module source

`build_mutant` renders the complete module source for one `CodeChunk` by replacing
the corresponding original function range:

```python
from pymut4se.mutation import build_mutant

module_source = build_mutant(mutant_chunk)
```

The function returns a string and does not modify `Module.source`. The supplied
chunk must be attached to a `Module` whose `source` is available.

For higher-order mutants, replacement boundaries come from the degree-zero
ancestor rather than the latest parent's changed `end_line`. This keeps code after
the original function intact when a mutation adds or removes lines.

AST unparsing removes a method's surrounding class indentation. `build_mutant`
restores indentation from the original module line before substitution. It also
preserves the module's `LF`, `CRLF`, or `CR` newline style and whether the replaced
source range ended with a newline.

Persistent chunks may lazy-load `parent` and `module`; keep them attached to an
open session or pre-load those relationships before rendering.

## Implementing an operator

Operators implement the `Mutation` interface. AST-based operators can inherit
from `PythonASTMutation`, which parses dedented function and method chunks.

Use `build_mutated_code_chunk` to preserve source identity and mutation metadata:

```python
return build_mutated_code_chunk(
    original=chunk,
    mutated_code=new_source,
    relative_line_changed=node.lineno,
    relative_column_changed=node.col_offset,
    mutation_type="conditional",
    mutation_operator=type(self).__name__,
)
```

Relative line numbers are converted to project source lines. Columns are stored
as one-based positions. The helper increments the mutation degree, links the new
chunk to both its immediate parent and degree-zero original, and connects it to
the surrounding ORM graph.

See [Generic mutation operators](operators.md) for the implemented operator set,
expected mutant counts, metadata, and limitations.
