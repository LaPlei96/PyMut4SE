from __future__ import annotations

import ast
from dataclasses import dataclass

from pymut4se.model import CodeChunk
from pymut4se.mutation.generic.utils import build_mutants_from_points, collect_mutation_points
from pymut4se.mutation.mutation import PythonASTMutation


@dataclass(frozen=True)
class _LogicalConnectorPoint:
    """A Boolean expression and its replacement connector."""

    node_index: int
    operator: ast.boolop
    line: int
    col_offset: int


class _LogicalConnectorCollector:
    """Collect one inverse connector for every Boolean expression."""

    def __init__(self) -> None:
        self.mutations: list[_LogicalConnectorPoint] = []

    def visit(self, node: ast.AST) -> None:
        boolean_expressions = (child for child in ast.walk(node) if isinstance(child, ast.BoolOp))
        for node_index, node in enumerate(boolean_expressions):
            replacement = ast.Or() if isinstance(node.op, ast.And) else ast.And()
            self.mutations.append(
                _LogicalConnectorPoint(
                    node_index=node_index,
                    operator=replacement,
                    line=node.lineno,
                    col_offset=node.col_offset,
                )
            )


class LogicalConnectorMutation(PythonASTMutation):
    """Replace each ``and`` connector with ``or``, and vice versa."""

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_LogicalConnectorPoint]:
        return collect_mutation_points(_LogicalConnectorCollector(), parsed_code)

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_LogicalConnectorPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="logical_connector",
            mutation_operator=lambda point: type(point.operator).__name__,
            apply_mutation=_apply_logical_connector_mutation,
        )


def _apply_logical_connector_mutation(tree: ast.AST, point: _LogicalConnectorPoint) -> None:
    boolean_expressions = (node for node in ast.walk(tree) if isinstance(node, ast.BoolOp))
    for node_index, node in enumerate(boolean_expressions):
        if node_index == point.node_index:
            node.op = point.operator
            return
