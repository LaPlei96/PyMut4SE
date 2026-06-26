from __future__ import annotations

import ast
from dataclasses import dataclass

from pymut4se.model import CodeChunk
from pymut4se.mutation.generic.utils import build_mutants_from_points, first_function, has_same_location
from pymut4se.mutation.mutation import PythonASTMutation


@dataclass(frozen=True)
class _DecoratorPoint:
    """One decorator selected for deletion from the represented function."""

    decorator_index: int
    decorator_name: str
    function_line: int
    function_col_offset: int
    line: int
    col_offset: int


class DeleteDecoratorMutation(PythonASTMutation):
    """Delete each decorator from the represented function independently."""

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_DecoratorPoint]:
        function = first_function(parsed_code)
        if function is None:
            return []
        return [
            _DecoratorPoint(
                decorator_index=index,
                decorator_name=ast.unparse(decorator),
                function_line=function.lineno,
                function_col_offset=function.col_offset,
                line=decorator.lineno,
                col_offset=max(0, decorator.col_offset - 1),
            )
            for index, decorator in enumerate(function.decorator_list)
        ]

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_DecoratorPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="delete_decorator",
            mutation_operator=lambda point: f"delete:{point.decorator_name}",
            apply_mutation=_apply_decorator_deletion,
        )


def _apply_decorator_deletion(tree: ast.AST, point: _DecoratorPoint) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not has_same_location(node, point.function_line, point.function_col_offset):
            continue
        if point.decorator_index < len(node.decorator_list):
            del node.decorator_list[point.decorator_index]
        return
