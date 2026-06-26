from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import ClassVar

from pymut4se.model import CodeChunk
from pymut4se.mutation.generic.utils import build_mutants_from_points, has_same_location
from pymut4se.mutation.mutation import PythonASTMutation


@dataclass(frozen=True)
class _DeletePoint:
    """One statement selected for deletion."""

    node_type: type[ast.stmt]
    line: int
    col_offset: int


class _DeleteStatementMutation(PythonASTMutation):
    """Shared implementation for deleting selected statement categories."""

    statement_types: ClassVar[tuple[type[ast.stmt], ...]]
    mutation_type: ClassVar[str]

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_DeletePoint]:
        return [
            _DeletePoint(type(node), node.lineno, node.col_offset)
            for node in ast.walk(parsed_code)
            if isinstance(node, self.statement_types)
        ]

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_DeletePoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type=self.mutation_type,
            mutation_operator=lambda point: point.node_type.__name__,
            apply_mutation=_apply_delete_mutation,
        )


class _DeleteNode(ast.NodeTransformer):
    """Remove one statement at an exact source location."""

    def __init__(self, point: _DeletePoint):
        self.point = point

    def visit_Assign(self, node: ast.Assign) -> ast.AST | None:
        return self._visit_statement(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST | None:
        return self._visit_statement(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST | None:
        return self._visit_statement(node)

    def visit_If(self, node: ast.If) -> ast.AST | None:
        return self._visit_statement(node)

    def visit_While(self, node: ast.While) -> ast.AST | None:
        return self._visit_statement(node)

    def visit_Return(self, node: ast.Return) -> ast.AST | None:
        return self._visit_statement(node)

    def _visit_statement(self, node: ast.stmt) -> ast.AST | None:
        if isinstance(node, self.point.node_type) and has_same_location(node, self.point.line, self.point.col_offset):
            return None
        return super().generic_visit(node)


def _apply_delete_mutation(tree: ast.AST, point: _DeletePoint) -> None:
    _DeleteNode(point).visit(tree)
    _repair_empty_bodies(tree, point)


def _repair_empty_bodies(tree: ast.AST, point: _DeletePoint) -> None:
    """Insert ``pass`` where statement deletion leaves a required body empty."""
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and not body and _requires_nonempty_body(node):
            body.append(ast.Pass(lineno=point.line, col_offset=point.col_offset))
        if isinstance(node, (ast.Try, ast.TryStar)) and not node.handlers and not node.finalbody:
            node.finalbody.append(ast.Pass(lineno=point.line, col_offset=point.col_offset))


def _requires_nonempty_body(node: ast.AST) -> bool:
    return isinstance(
        node,
        (
            ast.AsyncFor,
            ast.AsyncFunctionDef,
            ast.AsyncWith,
            ast.ClassDef,
            ast.ExceptHandler,
            ast.For,
            ast.FunctionDef,
            ast.If,
            ast.Try,
            ast.TryStar,
            ast.While,
            ast.With,
            ast.match_case,
        ),
    )
