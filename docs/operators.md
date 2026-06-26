# Generic Mutation Operators

This page is the operator catalogue. Use it when you need to choose mutation
operators or understand the metadata generated for each mutant.

For the high-level API, pass friendly names:

```python
mutants = workspace.mutate_chunks_with_tests(
    workspace.chunks,
    operators=["arithmetic", "relational", "logical-connector"],
)
```

Use `"all"` to apply every implemented operator:

```python
mutants = workspace.mutate_chunks_with_tests(workspace.chunks, "all")
```

For lower-level workflows, import operator classes from
`pymut4se.mutation.generic` and pass them to `generate_mutants()`.

## Choosing Operators

Start small. A focused set is easier to interpret than a large first run:

| Goal | Good starting operators |
| --- | --- |
| Numeric calculations | `arithmetic`, `constant-replacement`, `unary` |
| Branch and boundary behavior | `relational`, `logical-connector`, `boolean-replacement` |
| Missing or skipped statements | `delete-return`, `delete-if-statement`, `delete-assignment`, `return-pass` |
| Call-site mistakes | `swap-arguments`, `optional-parameter-caller` |
| Function signature/default behavior | `optional-parameter-callee`, `type-cast`, `add-if-not-null` |

Every mutant records:

| Field | Meaning |
| --- | --- |
| `mutation_type` | Broad operator family, such as `arithmetic`. |
| `mutation_operator` | Concrete replacement, such as `Sub` or `swap:0:1`. |
| `line_changed` / `column_changed` | One-based position in the original source. |

## Operator Summary

| Operator | Intent | Documentation |
| --- | --- | --- |
| `ArithmeticMutation` | Replace binary arithmetic, shift, and bitwise operators. | [Arithmetic mutation](#arithmetic-mutation) |
| `BooleanReplacementMutation` | Invert Boolean literals. | [Boolean replacement](#boolean-replacement) |
| `ConstantReplacementMutation` | Perturb numeric constants and their signs. | [Constant replacement](#constant-replacement-mutation) |
| `ControlReplacementMutation` | Exchange `break` and `continue` statements. | [Control replacement](#control-replacement-mutation) |
| `DeleteAssignmentMutation` | Remove an assignment statement. | [Assignment deletion](#assignment-deletion) |
| `DeleteDecoratorMutation` | Remove decorators from a function or method. | [Decorator deletion](#delete-decorator-mutation) |
| `DeleteIfStatementMutation` | Remove a complete conditional statement. | [If-statement deletion](#if-statement-deletion) |
| `DeleteReturnMutation` | Remove an explicit return statement. | [Return deletion](#return-deletion) |
| `DeleteWhileMutation` | Remove a complete `while` loop. | [While-loop deletion](#while-loop-deletion) |
| `IfNotNullMutation` | Guard a function body against a `None` parameter. | [If-not-null mutation](#if-not-null-mutation) |
| `LogicalConnectorMutation` | Exchange `and` and `or` connectors. | [Logical-connector mutation](#logical-connector-mutation) |
| `OptionalParamCalleeMutation` | Replace defaults in function declarations. | [Callee-side optional defaults](#callee-side-optional-defaults) |
| `OptionalParamCallerMutation` | Add or remove optional arguments at call sites. | [Caller-side optional parameters](#optional-parameter-mutation) |
| `RelationalMutation` | Change comparison conditions and boundaries. | [Relational mutation](#relational-mutation) |
| `ReturnPassMutation` | Cancel a function's executable body. | [Return-pass mutation](#return-pass-mutation) |
| `SwapArgumentsMutation` | Swap positional arguments at call sites. | [Swap-arguments mutation](#swap-arguments-mutation) |
| `TypeCastMutation` | Cast a parameter before it is used. | [Type-cast mutation](#type-cast-mutation) |
| `UnaryMutation` | Replace negation, sign, and bitwise inversion operators. | [Unary mutation](#unary-mutation) |

Lower-level imports:

```python
from pymut4se.mutation.generic import (
    ArithmeticMutation,
    BooleanReplacementMutation,
    ConstantReplacementMutation,
    ControlReplacementMutation,
    DeleteAssignmentMutation,
    DeleteDecoratorMutation,
    DeleteIfStatementMutation,
    DeleteReturnMutation,
    DeleteWhileMutation,
    IfNotNullMutation,
    LogicalConnectorMutation,
    OptionalParamCalleeMutation,
    OptionalParamCallerMutation,
    RelationalMutation,
    ReturnPassMutation,
    SwapArgumentsMutation,
    TypeCastMutation,
    UnaryMutation,
)
```

They accept function-sized `CodeChunk` objects and return independent degree-one
chunks. Use `generate_mutants` to apply several operators to a chunk, module, or
package and to generate higher-order mutants.

## Arithmetic mutation

`ArithmeticMutation` checks whether a test suite notices that a calculation uses
the wrong binary operator. For example, this source:

```python
return subtotal + tax
```

produces independent mutants such as:

```python
return subtotal - tax
return subtotal * tax
```

The operator finds every binary expression and replaces its operator with every
other supported operator:

| Category | Operators |
| --- | --- |
| Arithmetic | `+`, `-`, `*`, `@`, `/`, `%`, `**`, `//` |
| Shift | `<<`, `>>` |
| Bitwise | `|`, `^` |

For example, one `+` expression produces eleven mutants. Each mutant changes one
binary expression. Its metadata uses `mutation_type="arithmetic"` and records the
replacement AST name, such as `Sub` or `FloorDiv`, in `mutation_operator`.

## Relational mutation

`RelationalMutation` checks whether tests enforce comparison boundaries and
conditions. For example:

```python
if minimum <= value:
```

produces independent alternatives such as:

```python
if minimum < value:
if minimum != value:
```

The operator replaces each comparison operator, including each position of a
chained comparison. Supported operators are:

```text
==  !=  <  <=  >  >=  is  is not  in  not in
```

One comparison operator produces nine mutants. A two-part chained comparison
produces eighteen. Metadata uses `mutation_type="relational"` and the replacement
AST name, such as `GtE`, as `mutation_operator`.

## Constant-replacement mutation

`ConstantReplacementMutation` checks whether tests depend on a numeric constant's
exact value and sign. For example:

```python
timeout = 5
```

produces four independent replacements:

```python
timeout = 5 + 1
timeout = 5 - 1
timeout = abs(5)
timeout = -5
```

The operator creates four expression variants for every numeric literal:

| Mutation operator | Replacement for `value` |
| --- | --- |
| `add_one` | `value + 1` |
| `subtract_one` | `value - 1` |
| `absolute` | `abs(value)` |
| `negate` | `-value` |

Signed literals are treated as one value: `-5` becomes `-5 + 1`, `-5 - 1`,
`abs(-5)`, or `-(-5)` rather than mutating the unsigned child literal. Integers,
floats, and complex literals are supported. Booleans are explicitly excluded even
though Python represents `bool` as a subclass of `int`; strings, bytes, `None`,
and ellipsis are also ignored.

Each mutant changes one exact constant location. Metadata uses
`mutation_type="constant_replacement"` and one of the four table values as
`mutation_operator`. The expressions are not constant-folded, preserving which
mutation was applied in the generated source.

### Boolean replacement

`BooleanReplacementMutation` checks whether Boolean configuration and branch
values are asserted in the correct direction. Each literal is inverted:

```python
# Original
enabled = True

# Mutant
enabled = False
```

It is defined alongside numeric constant replacement but remains a separate
operator. Multiple Boolean literals are inverted independently. Defaults,
regular function bodies, and asynchronous functions are supported. Metadata uses
`mutation_type="boolean_replacement"` and
`mutation_operator="invert_boolean"`.

Keeping this separate from `ConstantReplacementMutation` prevents Python's
`bool`-is-an-`int` relationship from accidentally producing arithmetic Boolean
mutants.

## Control-replacement mutation

`ControlReplacementMutation` checks whether a loop should stop or skip directly
to its next iteration. It exchanges `break` and `continue` statements:

```python
# Original
for item in items:
    if item is None:
        continue
    process(item)

# Mutant
for item in items:
    if item is None:
        break
    process(item)
```

Each `break` or `continue` location produces one independent mutant. Statements
inside nested loops and synchronous or asynchronous functions are supported.
Replacing `break` with `continue` can make a loop execute for longer—or forever—which
is a valid mutation outcome and should be handled by execution timeouts.

Metadata uses `mutation_type="control_replacement"` and stores
`replace_with_break` or `replace_with_continue` in `mutation_operator`.

## Delete-decorator mutation

`DeleteDecoratorMutation` checks whether a function's behavior depends on a
decorator. It removes one decorator at a time:

```python
# Original
@authenticated
@audit
def update_account():
    ...

# One mutant
@audit
def update_account():
    ...
```

Only decorators on the function or method represented by the chunk are selected;
decorators on nested functions are left unchanged. Regular decorator names,
attribute access such as `@registry.handler`, and calls such as `@cache(60)` are
supported, as are synchronous and asynchronous functions.

Project exploration includes decorator lines in a function's `CodeChunk`, so
building the complete mutant module removes the selected decorator from the
original source range. Undecorated chunks produce no mutants.

Metadata uses `mutation_type="delete_decorator"` and records the removed
decorator as `delete:<decorator>` in `mutation_operator`.

## Unary mutation

`UnaryMutation` checks whether code applies the correct negation, sign, or bitwise
inversion. For example:

```python
return -value
```

produces independent mutants including:

```python
return +value
return not value
return ~value
```

The operator replaces each unary expression with every other supported unary
operator:

| Syntax | AST name |
| --- | --- |
| `~value` | `Invert` |
| `not value` | `Not` |
| `+value` | `UAdd` |
| `-value` | `USub` |

One unary expression produces three mutants. When a chunk contains multiple or
nested unary expressions, each mutant changes exactly one location. Metadata uses
`mutation_type="unary"` and the replacement AST name as `mutation_operator`.

All replacements are syntactically valid, but their runtime result types can
differ substantially: `not` produces a Boolean while arithmetic and inversion
operators depend on operand support.

## Statement-deletion mutations

Statement-deletion operators check whether a statement is necessary for the
observed behavior. Each mutant removes one statement. The family contains four
independently selectable operators:

| Operator | Deleted AST statements | Mutation type |
| --- | --- | --- |
| `DeleteAssignmentMutation` | `Assign`, `AnnAssign`, `AugAssign` | `delete_assignment` |
| `DeleteIfStatementMutation` | Complete `If`, including `else` | `delete_if_statement` |
| `DeleteWhileMutation` | Complete `While`, including `else` | `delete_while` |
| `DeleteReturnMutation` | `Return` | `delete_return` |

### Assignment deletion

`DeleteAssignmentMutation` checks whether a stored value affects the eventual
result. It removes regular, annotated, and augmented assignments one at a time:

```python
# Original
total = subtotal + tax
return total

# Mutant
return total
```

### If-statement deletion

`DeleteIfStatementMutation` checks whether an entire conditional branch is
necessary. It removes the complete statement, including any `else` branch:

```python
# Original
if value < 0:
    return "negative"
return "positive"

# Mutant
return "positive"
```

### While-loop deletion

`DeleteWhileMutation` checks whether a loop contributes to the result or side
effects. It removes the complete loop, including any `else` branch:

```python
# Original
while pending:
    process(pending.pop())
return "done"

# Mutant
return "done"
```

### Return deletion

`DeleteReturnMutation` checks whether an explicit return controls the observed
value or flow. Removing it allows execution to continue or the function to fall
through to `None`:

```python
# Original
if cached:
    return cached_value
return calculate()

# One mutant
if cached:
    pass
return calculate()
```

Each mutant deletes one exact statement. The `mutation_operator` metadata records
the deleted AST class, such as `Assign`, `If`, `While`, or `Return`.

Deleting the only statement from a required Python body would normally produce an
invalid AST. The shared deletion implementation inserts `pass` when necessary in
functions, async functions, classes, branches, loops, context managers, exception
handlers, `try` blocks, and pattern-match cases. It also repairs a required empty
`finally` block.

Deleting `if` or `while` removes the complete compound statement rather than
lifting its body into the parent scope. Deleting a return allows normal control
flow to continue and may cause the function to return `None` implicitly.

## Return-pass mutation

`ReturnPassMutation` checks whether calling a function has any observable effect
by cancelling its entire executable body:

```python
# Original
def notify(user):
    send_email(user)
    return True

# Mutant
def notify(user):
    pass
```

It replaces the executable body with one `pass` statement. Since `pass` itself is a
no-op, merely inserting it before the existing body would not cancel execution;
the existing statements must be removed.

Function docstrings are preserved as the first statement, followed by `pass`.
Synchronous and asynchronous functions are supported. Nested functions disappear
with the replaced outer body, while decorators and the function signature remain
unchanged. Functions whose executable body is already only `pass` are skipped to
avoid equivalent mutants.

The resulting function returns `None` through normal fall-through. Metadata uses
`mutation_type="return_pass"` and
`mutation_operator="replace_body_with_pass"`.

## Swap-arguments mutation

`SwapArgumentsMutation` checks whether a caller supplies positional values in the
correct order. It swaps one pair of arguments at a time:

```python
# Original
content = read(start, end)

# Mutant
content = read(end, start)
```

A call with two positional arguments produces one mutant. A call with three
positional arguments produces three mutants—one for each possible pair. When a
chunk contains multiple calls, each mutant changes only one call site. Direct,
attribute, nested, synchronous, and asynchronous calls are supported.

Keyword arguments retain their names and values and are not included in swaps.
Calls containing a starred positional expansion such as `read(*bounds, end)` are
skipped because their concrete positional bindings cannot be established
statically.

Metadata uses `mutation_type="swap_arguments"` and stores the zero-based swapped
positions as `swap:<left>:<right>` in `mutation_operator`.

## Type-cast mutation

`TypeCastMutation` checks whether behavior depends on a parameter retaining its
incoming type. For example, one mutant converts `value` to an integer before the
function uses it:

```python
# Original
def normalize(value):
    return value

# Mutant
def normalize(value):
    value = int(value)
    return value
```

It creates `int`, `str`, and `float` variants for positional-only, regular
positional, and keyword-only parameters. Conventional receiver parameters named
`self` or `cls` are skipped. Variadic `*args` and `**kwargs` are not cast.

Function docstrings remain the first statement. Only the outer function represented
by the chunk is changed; nested functions are left untouched. Synchronous and
asynchronous functions are supported. Metadata uses `mutation_type="cast_type"`
and a value such as `value:int` as `mutation_operator`.

## If-not-null mutation

`IfNotNullMutation` checks whether a function should do nothing when a parameter
is `None`. For example:

```python
# Original
def save(value):
    repository.add(value)

# Mutant
def save(value):
    if value is not None:
        repository.add(value)
```

The operator creates one mutant per supported parameter by wrapping the function
body in a guard:

```python
if value is not None:
    ...
```

It follows the same parameter, docstring, nested-function, and async rules as
`TypeCastMutation`. Metadata uses `mutation_type="if_not_null"` and the guarded
parameter name as `mutation_operator`.

## Logical-connector mutation

`LogicalConnectorMutation` checks whether a condition requires every operand or
only one operand to be true. It exchanges `and` and `or`:

```python
# Original
if authenticated and authorized:
    grant_access()

# Mutant
if authenticated or authorized:
    grant_access()
```

Each Boolean expression produces one mutant. A chain is treated as a single
expression, so `first and second and third` becomes
`first or second or third`. Nested Boolean expressions are mutated independently,
with exactly one connector changed in each mutant. Synchronous and asynchronous
functions are supported.

Metadata uses `mutation_type="logical_connector"`. The replacement connector's
AST name, `And` or `Or`, is stored in `mutation_operator`.

## Optional-parameter mutation

`OptionalParamCallerMutation` checks whether callers rely on a callee's default
argument or on an explicitly supplied value. For example, it can produce either
of these caller-side changes:

```python
# Add an omitted optional argument
load()                 # original
load(limit=0)          # mutant

# Remove an explicit optional argument
load(limit=20)         # original
load()                 # mutant
```

It changes optional arguments at direct calls to functions defined in the same
module:

- An omitted defaulted parameter can be added as an explicit keyword argument.
- A supplied optional keyword argument can be removed so the declared default is
  used instead.

The operator resolves signatures from degree-zero sibling chunks through the
caller's `Module.code_chunks` relationship. It also supports nested functions
defined in the same chunk and synchronous or asynchronous functions.

```python
from pymut4se.mutation.generic import OptionalParamCallerMutation

operator = OptionalParamCallerMutation(
    fallback_literals={
        "int": 42,
        "list": ["mutated"],
        "__default__": None,
    }
)
mutants = operator.mutate(caller_chunk)
```

Values for added arguments are chosen in this order:

1. A compatible annotated local variable in the caller.
2. A configured fallback for the parameter annotation.
3. The built-in fallback for `int`, `float`, `str`, `list`, or `dict`.
4. The `__default__` fallback for an unknown or missing annotation.

Boolean defaults are inverted. If a fallback equals the declared default, the
operator changes common scalar and container values to avoid an equivalent
mutant. User-provided list, dictionary, and tuple contents are preserved.

The operator handles positional-only, regular positional, and keyword-only
defaults. It does not add an argument that was already supplied positionally or
by keyword. Calls containing `*args` or `**kwargs` are skipped for additions
because their effective bindings cannot be established statically. Explicit
optional keywords in those calls can still be removed safely.

Metadata uses `mutation_type="optional_param_caller"` and records `add:parameter` or
`remove:parameter` in `mutation_operator`.

Only direct calls such as `helper(...)` are currently resolved. Attribute calls
such as `object.helper(...)`, imports from other modules, and runtime signature
changes are outside this operator's current static scope.

### Callee-side optional defaults

`OptionalParamCalleeMutation` checks whether callers that omit an optional
argument depend on its declared default. It changes the callee rather than its
call sites. For example:

```python
# Original
def load(limit: int = 10, *, cached: bool = False):
    ...

# Independent mutants
def load(limit: int = 0, *, cached: bool = False):
    ...

def load(limit: int = 10, *, cached: bool = True):
    ...
```

Existing callers are left unchanged; calls that omit the parameter observe the
changed default. The same fallback configuration accepted by
`OptionalParamCallerMutation` is supported.

The operator mutates positional-only, regular positional, and keyword-only
defaults on the outer synchronous or asynchronous function represented by the
chunk. Nested-function defaults are not changed as collateral mutations. Metadata
uses `mutation_type="optional_param_callee"` and a value such as
`replace_default:limit` as `mutation_operator`.

## Generation and persistence

```python
from pymut4se.mutation import generate_mutants
from pymut4se.mutation.generic import ArithmeticMutation, RelationalMutation

mutants = generate_mutants(
    target=module,
    mutation_operators=[ArithmeticMutation, RelationalMutation],
    max_degree=2,
)
```

Generated chunks retain their original module and project relationships. Their
`parent` relationships form the mutation chain, and committing the existing ORM
graph persists them.

## Interpretation and limitations

Operators guarantee syntactically valid Python, not type-correct or executable
behavior for every input. For example, matrix multiplication may be invalid for
scalar operands, and replacing ordering with membership may raise at runtime.
Such failures are valid mutation outcomes and should be classified by the mutation
execution phase.

Location metadata is one-based and refers to the original project source. AST
unparsing normalizes formatting, so mutated source text may not preserve the
original whitespace or quote style.

Files that do not yet contain implementations are intentionally not exported or
included in this operator reference.
