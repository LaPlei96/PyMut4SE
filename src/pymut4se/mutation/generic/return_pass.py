from __future__ import annotations

import ast
from dataclasses import dataclass

from pymut4se.model import CodeChunk
from pymut4se.mutation.generic.utils import (
    body_insertion_index,
    body_insertion_line,
    build_mutants_from_points,
    first_function,
    has_same_location,
)
from pymut4se.mutation.mutation import PythonASTMutation


@dataclass(frozen=True)
class _ReturnPassPoint:
    """The outer function body to replace with ``pass``."""

    line: int
    col_offset: int
    function_line: int
    function_col_offset: int


class ReturnPassMutation(PythonASTMutation):
    """Replace a function body with ``pass`` so it returns ``None``."""

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_ReturnPassPoint]:
        function = first_function(parsed_code)
        if function is None or _already_pass_only(function):
            return []
        return [
            _ReturnPassPoint(
                line=body_insertion_line(function),
                col_offset=function.col_offset + 4,
                function_line=function.lineno,
                function_col_offset=function.col_offset,
            )
        ]

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_ReturnPassPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="return_pass",
            mutation_operator=lambda _point: "replace_body_with_pass",
            apply_mutation=_apply_return_pass_mutation,
        )


class _ReturnPassTransformer(ast.NodeTransformer):
    """Replace one exact synchronous or asynchronous function body."""

    def __init__(self, point: _ReturnPassPoint):
        self.point = point

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        return self._replace_body(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        return self._replace_body(node)

    def _replace_body(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        if not has_same_location(node, self.point.function_line, self.point.function_col_offset):
            return node
        docstring_end = body_insertion_index(node)
        location_source = node.body[docstring_end] if docstring_end < len(node.body) else node
        pass_statement = ast.copy_location(ast.Pass(), location_source)
        node.body = [*node.body[:docstring_end], pass_statement]
        return node


def _apply_return_pass_mutation(tree: ast.AST, point: _ReturnPassPoint) -> None:
    _ReturnPassTransformer(point).visit(tree)


def _already_pass_only(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = function.body[body_insertion_index(function) :]
    return len(body) == 1 and isinstance(body[0], ast.Pass)
