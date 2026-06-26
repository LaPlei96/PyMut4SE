from abc import ABC, abstractmethod
from ast import Module, parse
from textwrap import dedent
from typing import Any, Optional

from pymut4se.model.code_chunk import CodeChunk


class Mutation(ABC):
    """Interface for parsing, finding mutation points, and generating mutants."""

    @abstractmethod
    def _parse(self, code: CodeChunk) -> Any:
        """Parse the given code chunk and return a structured representation."""
        pass

    @abstractmethod
    def _find_mutation_points(self, parsed_code: Any) -> list:
        """Find all possible mutation points in the parsed code."""
        pass

    @abstractmethod
    def _apply_mutation(self, code: CodeChunk, parsed_code: Any, mutation_point: list) -> list[CodeChunk]:
        """Apply mutations and generate mutated code chunks."""
        pass

    def mutate(self, code: CodeChunk) -> list[CodeChunk]:
        """Parse code, find mutation points, and generate mutated code chunks."""
        parsed_code = self._parse(code)
        mutation_points = self._find_mutation_points(parsed_code)
        mutated_codes = self._apply_mutation(code, parsed_code, mutation_points)
        return mutated_codes


class PythonASTMutation(Mutation):
    """Base class for mutation operators that work on Python ASTs."""

    def _parse(self, code: CodeChunk) -> Module:
        """Parse a chunk as standalone Python source.

        Method chunks discovered from classes keep their original indentation;
        dedenting allows them to be parsed independently.
        """
        tree = parse(dedent(code.code))
        return tree


def build_mutated_code_chunk(
    original: CodeChunk,
    mutated_code: str,
    relative_line_changed: Optional[int],
    relative_column_changed: Optional[int],
    mutation_type: str,
    mutation_operator: str,
) -> CodeChunk:
    """Build and connect a mutant while preserving its parent's context."""
    original_ancestor = _original_ancestor(original)
    line_count = max(1, len(mutated_code.splitlines()))
    line_changed = None
    if relative_line_changed is not None:
        line_changed = original.start_line + relative_line_changed - 1
    column_changed = None
    if relative_column_changed is not None:
        column_changed = relative_column_changed + 1

    mutant = CodeChunk(
        code=mutated_code,
        module_id=original.module_id,
        function_name=original.function_name,
        chunk_type=original.chunk_type,
        start_line=original.start_line,
        end_line=original.start_line + line_count - 1,
        mutation_degree=original.mutation_degree + 1,
        original_id=original_ancestor.chunk_id,
        parent_id=original.chunk_id,
        line_changed=line_changed,
        column_changed=column_changed,
        mutation_type=mutation_type,
        mutation_operator=mutation_operator,
        project_id=original.project_id,
    )
    mutant.parent = original
    mutant.original = original_ancestor
    if original.module is not None:
        mutant.module = original.module
    if original.project is not None:
        mutant.project = original.project
    return mutant


def _original_ancestor(code_chunk: CodeChunk) -> CodeChunk:
    if code_chunk.mutation_degree == 0:
        return code_chunk
    if code_chunk.original is not None:
        return code_chunk.original
    current = code_chunk
    seen_ids = set()
    while current.parent is not None and current.chunk_id not in seen_ids:
        seen_ids.add(current.chunk_id)
        current = current.parent
    return current
