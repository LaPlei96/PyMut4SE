from __future__ import annotations

import ast
from dataclasses import dataclass

from pymut4se.mutation.generic.utils import build_mutants_from_points, collect_mutation_points, has_same_location
from pymut4se.mutation.mutation import PythonASTMutation
from pymut4se.model.code_chunk import CodeChunk

COMPARISON_OPERATORS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn)


@dataclass(frozen=True)
class _RelationPoint:
    """A Relation operator that can be replaced."""

    operator: ast.cmpop
    operator_index: int
    line: int
    col_offset: int


class _RelationalASTMutation(ast.NodeTransformer):
    """Collect replacement Relation operators."""

    def __init__(self):
        self.mutations: list[_RelationPoint] = []

    def visit_Compare(self, node: ast.Compare) -> ast.Compare:
        for operator_type in COMPARISON_OPERATORS:
            for i, op in enumerate(node.ops):
                if not isinstance(op, operator_type):
                    self.mutations.append(
                        _RelationPoint(
                            operator=operator_type(),
                            operator_index=i,
                            line=node.lineno,
                            col_offset=node.col_offset,
                        )
                    )
        self.generic_visit(node)
        return node


class RelationalMutation(PythonASTMutation):
    """Replace comparison operators with alternative Relation."""

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_RelationPoint]:
        return collect_mutation_points(_RelationalASTMutation(), parsed_code)

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_RelationPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="relational",
            mutation_operator=lambda point: type(point.operator).__name__,
            apply_mutation=_apply_relation_mutation,
        )


def _apply_relation_mutation(tree: ast.AST, point: _RelationPoint) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and has_same_location(node, point.line, point.col_offset):
            node.ops[point.operator_index] = point.operator
