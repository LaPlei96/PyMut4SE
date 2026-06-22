from __future__ import annotations

import ast
import copy
from collections.abc import Callable, Iterable
from typing import Any, Protocol, TypeVar

from pymut4se.mutation.mutation import build_mutated_code_chunk
from pymut4se.model.code_chunk import CodeChunk


class SourceMutationPoint(Protocol):
    """Mutation point carrying a source location relative to the parsed chunk."""

    line: int
    col_offset: int


PointT = TypeVar("PointT", bound=SourceMutationPoint)


class MutationPointCollector(Protocol[PointT]):
    """AST visitor exposing the points collected during traversal."""

    mutations: list[PointT]

    def visit(self, node: ast.AST) -> Any:
        """Visit an AST node."""


def build_mutants_from_points(
    *,
    original: CodeChunk,
    parsed_code: ast.AST,
    mutation_points: Iterable[PointT],
    mutation_type: str,
    mutation_operator: Callable[[PointT], str],
    apply_mutation: Callable[[ast.AST, PointT], None],
) -> list[CodeChunk]:
    """Apply each mutation point to a copied tree and build mutated chunks."""
    mutated_chunks = []
    for point in mutation_points:
        new_tree = copy.deepcopy(parsed_code)
        apply_mutation(new_tree, point)
        ast.fix_missing_locations(new_tree)
        mutated_chunks.append(
            build_mutated_code_chunk(
                original=original,
                mutated_code=ast.unparse(new_tree),
                relative_line_changed=point.line,
                relative_column_changed=point.col_offset,
                mutation_type=mutation_type,
                mutation_operator=mutation_operator(point),
            )
        )
    return mutated_chunks


def collect_mutation_points(visitor: MutationPointCollector[PointT], parsed_code: ast.AST) -> list[PointT]:
    """Run a visitor that exposes a ``mutations`` list."""
    visitor.visit(parsed_code)
    return visitor.mutations


def first_function(tree: ast.AST) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Return the first function definition in a parsed chunk."""
    return next(
        (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))),
        None,
    )


def function_parameters(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    """Return parameters suitable for guards and scalar type casts."""
    parameters = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
    return [parameter for parameter in parameters if parameter.arg not in {"self", "cls"}]


def body_insertion_index(function: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Return an insertion index that preserves a function docstring."""
    if function.body and _is_docstring(function.body[0]):
        return 1
    return 0


def body_insertion_line(function: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Return the source line at which a new first body statement is inserted."""
    index = body_insertion_index(function)
    if index and function.body[0].end_lineno is not None:
        return function.body[0].end_lineno + 1
    return function.lineno + 1


def _is_docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def has_same_location(node: ast.AST, line: int, col_offset: int) -> bool:
    """Return whether a node starts at the given source location."""
    return getattr(node, "lineno", None) == line and getattr(node, "col_offset", None) == col_offset
