from pymut4se.model.code_chunk import CodeChunk
from abc import ABC, abstractmethod
from typing import Any


class Mutation(ABC):
    """The Mutation class defines the interface for all mutation types. It includes methods for parsing code, finding mutation points, applying mutations, and generating mutated code chunks.
    """
    @abstractmethod
    def _parse(self, code: CodeChunk) -> Any:
        """Parses the given code chunk and returns a structured representation (e.g., an AST for Python code).
            :param code: The code chunk to be parsed.
            :return: A structured representation of the code (e.g., an AST).
        """
        pass

    @abstractmethod
    def _find_mutation_points(self, parsed_code: Any) -> list:
        """Finds all possible mutation points in the parsed code.
            :param parsed_code: The structured representation of the code.
            :return: A list of mutation points.
        """
        pass

    @abstractmethod
    def _apply_mutation(self, code: CodeChunk, parsed_code: Any, mutation_point: list) -> list[CodeChunk]:
        """Applies the mutation at the specified mutation point and generates mutated code chunks.
            :param code: The original code chunk.
            :param parsed_code: The structured representation of the original code.
            :param mutation_point: The specific mutation point to apply the mutation.
            :return: A list of mutated code chunks.
        """
        pass

    def mutate(self, code: CodeChunk) -> list[CodeChunk]:
        """The mutate method orchestrates the mutation process by parsing the code, finding mutation points, and applying mutations to generate mutated code chunks.
            :param code: The original code chunk to be mutated. 
            :return: A list of mutated code chunks generated from the original code.
        """
        parsed_code = self._parse(code)
        mutation_points = self._find_mutation_points(parsed_code)
        mutated_codes = self._apply_mutation(code, parsed_code, mutation_points)
        return mutated_codes
