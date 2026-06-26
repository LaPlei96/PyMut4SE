from __future__ import annotations

import ast
from dataclasses import dataclass

from pymut4se.mutation.generic.utils import build_mutants_from_points, collect_mutation_points, has_same_location
from pymut4se.mutation.mutation import PythonASTMutation
from pymut4se.model.code_chunk import CodeChunk

ARITHMETIC_OPERATORS = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.MatMult,
    ast.Div,
    ast.Mod,
    ast.Pow,
    ast.LShift,
    ast.RShift,
    ast.BitOr,
    ast.BitXor,
    ast.FloorDiv,
)


@dataclass(frozen=True)
class _ArithmeticPoint:
    """A binary operation that can receive a replacement operator."""

    operator: ast.operator
    line: int
    col_offset: int


class _ArithmeticASTMutation(ast.NodeTransformer):
    """Collect replacement arithmetic operators for binary expressions."""

    def __init__(self):
        self.mutations: list[_ArithmeticPoint] = []

    def visit_BinOp(self, node: ast.BinOp) -> ast.BinOp:
        for operator_type in ARITHMETIC_OPERATORS:
            if not isinstance(node.op, operator_type):
                self.mutations.append(
                    _ArithmeticPoint(operator=operator_type(), line=node.lineno, col_offset=node.col_offset)
                )
        self.generic_visit(node)
        return node


class ArithmeticMutation(PythonASTMutation):
    """Replace arithmetic binary operators with alternative operators."""

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_ArithmeticPoint]:
        return collect_mutation_points(_ArithmeticASTMutation(), parsed_code)

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_ArithmeticPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="arithmetic",
            mutation_operator=lambda point: type(point.operator).__name__,
            apply_mutation=_apply_arithmetic_mutation,
        )


def _apply_arithmetic_mutation(tree: ast.AST, point: _ArithmeticPoint) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and has_same_location(node, point.line, point.col_offset):
            node.op = point.operator
