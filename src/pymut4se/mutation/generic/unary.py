from __future__ import annotations

import ast
from dataclasses import dataclass

from pymut4se.model import CodeChunk
from pymut4se.mutation.generic.utils import build_mutants_from_points, collect_mutation_points, has_same_location
from pymut4se.mutation.mutation import PythonASTMutation

UNARY_OPERATORS = (ast.Invert, ast.Not, ast.UAdd, ast.USub)


@dataclass(frozen=True)
class _UnaryPoint:
    """A unary expression and its replacement operator."""

    operator: ast.unaryop
    line: int
    col_offset: int


class _UnaryASTMutation(ast.NodeTransformer):
    """Collect alternative operators for every unary expression."""

    def __init__(self):
        self.mutations: list[_UnaryPoint] = []

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.UnaryOp:
        for operator_type in UNARY_OPERATORS:
            if not isinstance(node.op, operator_type):
                self.mutations.append(
                    _UnaryPoint(operator=operator_type(), line=node.lineno, col_offset=node.col_offset)
                )
        self.generic_visit(node)
        return node


class UnaryMutation(PythonASTMutation):
    """Replace unary operators with each alternative unary operator."""

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_UnaryPoint]:
        return collect_mutation_points(_UnaryASTMutation(), parsed_code)

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_UnaryPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="unary",
            mutation_operator=lambda point: type(point.operator).__name__,
            apply_mutation=_apply_unary_mutation,
        )


def _apply_unary_mutation(tree: ast.AST, point: _UnaryPoint) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.UnaryOp) and has_same_location(node, point.line, point.col_offset):
            node.op = point.operator
