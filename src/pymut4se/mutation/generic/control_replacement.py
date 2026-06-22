from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Literal

from pymut4se.model import CodeChunk
from pymut4se.mutation.generic.utils import build_mutants_from_points, collect_mutation_points, has_same_location
from pymut4se.mutation.mutation import PythonASTMutation


@dataclass(frozen=True)
class _ControlReplacementPoint:
    """A loop-control statement and its replacement."""

    replacement: Literal["break", "continue"]
    line: int
    col_offset: int


class _ControlReplacementCollector(ast.NodeVisitor):
    """Collect inverse replacements for ``break`` and ``continue`` statements."""

    def __init__(self) -> None:
        self.mutations: list[_ControlReplacementPoint] = []

    def visit_Break(self, node: ast.Break) -> None:
        self.mutations.append(
            _ControlReplacementPoint(replacement="continue", line=node.lineno, col_offset=node.col_offset)
        )

    def visit_Continue(self, node: ast.Continue) -> None:
        self.mutations.append(
            _ControlReplacementPoint(replacement="break", line=node.lineno, col_offset=node.col_offset)
        )


class ControlReplacementMutation(PythonASTMutation):
    """Replace each ``break`` statement with ``continue``, and vice versa."""

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_ControlReplacementPoint]:
        return collect_mutation_points(_ControlReplacementCollector(), parsed_code)

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_ControlReplacementPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="control_replacement",
            mutation_operator=lambda point: f"replace_with_{point.replacement}",
            apply_mutation=_apply_control_replacement,
        )


class _ControlStatementReplacer(ast.NodeTransformer):
    """Replace the control statement at one exact source location."""

    def __init__(self, point: _ControlReplacementPoint) -> None:
        self.point = point

    def visit_Break(self, node: ast.Break) -> ast.stmt:
        if self.point.replacement == "continue" and has_same_location(node, self.point.line, self.point.col_offset):
            return ast.copy_location(ast.Continue(), node)
        return node

    def visit_Continue(self, node: ast.Continue) -> ast.stmt:
        if self.point.replacement == "break" and has_same_location(node, self.point.line, self.point.col_offset):
            return ast.copy_location(ast.Break(), node)
        return node


def _apply_control_replacement(tree: ast.AST, point: _ControlReplacementPoint) -> None:
    _ControlStatementReplacer(point).visit(tree)
