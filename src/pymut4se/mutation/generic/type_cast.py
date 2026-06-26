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

CAST_TYPES = ("int", "str", "float")


@dataclass(frozen=True)
class _TypeCastPoint:
    """A function parameter that can be wrapped in a type cast."""

    variable_name: str
    cast_type: str
    line: int
    col_offset: int


class _TypeCastASTMutation(ast.NodeTransformer):
    """Insert a type cast assignment at the start of a function body."""

    def __init__(self, variable_name: str, cast_type: str):
        self.variable_name = variable_name
        self.cast_type = cast_type
        self.applied = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        return self._mutate_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        return self._mutate_function(node)

    def _mutate_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        if self.applied:
            return node
        new_assign = ast.Assign(
            targets=[ast.Name(id=self.variable_name, ctx=ast.Store())],
            value=ast.Call(
                func=ast.Name(id=self.cast_type, ctx=ast.Load()),
                args=[ast.Name(id=self.variable_name, ctx=ast.Load())],
                keywords=[],
            ),
        )
        insertion_index = body_insertion_index(node)
        ast.copy_location(new_assign, node.body[insertion_index] if insertion_index < len(node.body) else node)
        node.body.insert(insertion_index, new_assign)
        self.applied = True
        return node


class TypeCastMutation(PythonASTMutation):
    """Cast each function parameter to common builtin types."""

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_TypeCastPoint]:
        function_def = first_function(parsed_code)
        if function_def is None:
            return []

        return [
            _TypeCastPoint(
                variable_name=arg.arg,
                cast_type=cast_type,
                line=body_insertion_line(function_def),
                col_offset=function_def.col_offset + 4,
            )
            for arg in function_parameters(function_def)
            for cast_type in CAST_TYPES
        ]

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_TypeCastPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="cast_type",
            mutation_operator=lambda point: f"{point.variable_name}:{point.cast_type}",
            apply_mutation=_apply_type_cast_mutation,
        )


def _apply_type_cast_mutation(tree: ast.AST, point: _TypeCastPoint) -> None:
    _TypeCastASTMutation(point.variable_name, point.cast_type).visit(tree)
