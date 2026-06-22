from __future__ import annotations

import ast
from dataclasses import dataclass
from itertools import combinations

from pymut4se.model import CodeChunk
from pymut4se.mutation.generic.utils import build_mutants_from_points
from pymut4se.mutation.mutation import PythonASTMutation


@dataclass(frozen=True)
class _ArgumentSwapPoint:
    """Two positional arguments selected for swapping at one call site."""

    call_index: int
    left_index: int
    right_index: int
    line: int
    col_offset: int


class SwapArgumentsMutation(PythonASTMutation):
    """Swap each pair of positional arguments at eligible call sites."""

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_ArgumentSwapPoint]:
        mutation_points = []
        calls = (node for node in ast.walk(parsed_code) if isinstance(node, ast.Call))
        for call_index, call in enumerate(calls):
            if len(call.args) < 2 or any(isinstance(argument, ast.Starred) for argument in call.args):
                continue
            mutation_points.extend(
                _ArgumentSwapPoint(
                    call_index=call_index,
                    left_index=left_index,
                    right_index=right_index,
                    line=call.lineno,
                    col_offset=call.col_offset,
                )
                for left_index, right_index in combinations(range(len(call.args)), 2)
            )
        return mutation_points

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_ArgumentSwapPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="swap_arguments",
            mutation_operator=lambda point: f"swap:{point.left_index}:{point.right_index}",
            apply_mutation=_apply_argument_swap,
        )


def _apply_argument_swap(tree: ast.AST, point: _ArgumentSwapPoint) -> None:
    calls = (node for node in ast.walk(tree) if isinstance(node, ast.Call))
    for call_index, call in enumerate(calls):
        if call_index != point.call_index:
            continue
        call.args[point.left_index], call.args[point.right_index] = (
            call.args[point.right_index],
            call.args[point.left_index],
        )
        return
