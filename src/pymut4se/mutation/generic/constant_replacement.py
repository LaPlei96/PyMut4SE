from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Literal

from pymut4se.model import CodeChunk
from pymut4se.mutation.generic.utils import build_mutants_from_points, collect_mutation_points, has_same_location
from pymut4se.mutation.mutation import PythonASTMutation

ReplacementKind = Literal["add_one", "subtract_one", "absolute", "negate"]
REPLACEMENT_KINDS: tuple[ReplacementKind, ...] = ("add_one", "subtract_one", "absolute", "negate")
NumericValue = int | float | complex


@dataclass(frozen=True)
class _ConstantPoint:
    """A numeric literal and one replacement expression."""

    value: NumericValue
    replacement: ReplacementKind
    line: int
    col_offset: int
    signed_literal: bool


class _ConstantVisitor(ast.NodeVisitor):
    """Collect numeric constants while treating signed literals as one value."""

    def __init__(self):
        self.mutations: list[_ConstantPoint] = []

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if isinstance(node.op, (ast.UAdd, ast.USub)) and isinstance(node.operand, ast.Constant):
            value = _numeric_value(node.operand.value)
            if value is not None:
                signed_value = -value if isinstance(node.op, ast.USub) else value
                self._add_points(signed_value, node.lineno, node.col_offset, signed_literal=True)
                return
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        value = _numeric_value(node.value)
        if value is not None:
            self._add_points(value, node.lineno, node.col_offset, signed_literal=False)

    def _add_points(self, value: NumericValue, line: int, col_offset: int, *, signed_literal: bool) -> None:
        self.mutations.extend(
            _ConstantPoint(value, replacement, line, col_offset, signed_literal) for replacement in REPLACEMENT_KINDS
        )


class ConstantReplacementMutation(PythonASTMutation):
    """Replace numeric constants with ±1, absolute-value, and negation expressions."""

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_ConstantPoint]:
        return collect_mutation_points(_ConstantVisitor(), parsed_code)

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_ConstantPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="constant_replacement",
            mutation_operator=lambda point: point.replacement,
            apply_mutation=_apply_constant_mutation,
        )


@dataclass(frozen=True)
class _BooleanPoint:
    """A Boolean literal to invert."""

    line: int
    col_offset: int


class _BooleanVisitor(ast.NodeVisitor):
    """Collect Boolean literals independently from numeric constants."""

    def __init__(self):
        self.mutations: list[_BooleanPoint] = []

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, bool):
            self.mutations.append(_BooleanPoint(node.lineno, node.col_offset))


class BooleanReplacementMutation(PythonASTMutation):
    """Invert each Boolean literal from true to false or false to true."""

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_BooleanPoint]:
        return collect_mutation_points(_BooleanVisitor(), parsed_code)

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_BooleanPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="boolean_replacement",
            mutation_operator=lambda _point: "invert_boolean",
            apply_mutation=_apply_boolean_mutation,
        )


class _ConstantTransformer(ast.NodeTransformer):
    """Replace the constant at one exact source location."""

    def __init__(self, point: _ConstantPoint):
        self.point = point

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        if self.point.signed_literal and has_same_location(node, self.point.line, self.point.col_offset):
            return ast.copy_location(_replacement_expression(self.point.value, self.point.replacement), node)
        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if not self.point.signed_literal and has_same_location(node, self.point.line, self.point.col_offset):
            return ast.copy_location(_replacement_expression(self.point.value, self.point.replacement), node)
        return node


def _apply_constant_mutation(tree: ast.AST, point: _ConstantPoint) -> None:
    _ConstantTransformer(point).visit(tree)


def _apply_boolean_mutation(tree: ast.AST, point: _BooleanPoint) -> None:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, bool)
            and has_same_location(node, point.line, point.col_offset)
        ):
            node.value = not node.value
            return


def _numeric_value(value: object) -> NumericValue | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, complex)):
        return None
    return value


def _replacement_expression(value: NumericValue, replacement: ReplacementKind) -> ast.expr:
    constant = ast.Constant(value=value)
    if replacement == "add_one":
        return ast.BinOp(left=constant, op=ast.Add(), right=ast.Constant(value=1))
    if replacement == "subtract_one":
        return ast.BinOp(left=constant, op=ast.Sub(), right=ast.Constant(value=1))
    if replacement == "absolute":
        return ast.Call(func=ast.Name(id="abs", ctx=ast.Load()), args=[constant], keywords=[])
    return ast.UnaryOp(op=ast.USub(), operand=constant)
