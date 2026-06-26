from __future__ import annotations

import ast
from dataclasses import dataclass

from pymut4se.mutation.generic.utils import (
    body_insertion_index,
    body_insertion_line,
    build_mutants_from_points,
    first_function,
    function_parameters,
)
from pymut4se.mutation.mutation import PythonASTMutation
from pymut4se.model.code_chunk import CodeChunk


@dataclass(frozen=True)
class _IfNotNullPoint:
    """A function parameter used to guard the function body."""

    variable_name: str
    line: int
    col_offset: int


class _IfNotNullASTMutation(ast.NodeTransformer):
    """Wrap a function body in ``if parameter is not None``."""

    def __init__(self, variable_name: str):
        self.variable_name = variable_name
        self.applied = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        return self._mutate_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        return self._mutate_function(node)

    def _mutate_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        if self.applied:
            return node
        insertion_index = body_insertion_index(node)
        guarded_body: list[ast.stmt] = list(node.body[insertion_index:])
        if not guarded_body:
            guarded_body.append(ast.Pass())
        new_test = ast.Compare(
            left=ast.Name(id=self.variable_name, ctx=ast.Load()),
            ops=[ast.IsNot()],
            comparators=[ast.Constant(value=None)],
        )
        new_if = ast.If(
            test=new_test,
            body=guarded_body,
            orelse=[],
        )
        location_source = guarded_body[0] if guarded_body else node
        ast.copy_location(new_if, location_source)
        node.body = [*node.body[:insertion_index], new_if]
        self.applied = True
        return node


class IfNotNullMutation(PythonASTMutation):
    """Guard each function body with a not-None check on one parameter."""

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_IfNotNullPoint]:
        function_def = first_function(parsed_code)
        if function_def is None:
            return []
        return [
            _IfNotNullPoint(
                variable_name=arg.arg,
                line=body_insertion_line(function_def),
                col_offset=function_def.col_offset + 4,
            )
            for arg in function_parameters(function_def)
        ]

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_IfNotNullPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="if_not_null",
            mutation_operator=lambda point: point.variable_name,
            apply_mutation=_apply_if_not_null_mutation,
        )


def _apply_if_not_null_mutation(tree: ast.AST, point: _IfNotNullPoint) -> None:
    _IfNotNullASTMutation(point.variable_name).visit(tree)
