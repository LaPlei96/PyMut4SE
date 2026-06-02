from abc import ABC, abstractmethod

from pymut4se.model.code_chunk import CodeChunk
from pymut4se.model.input import Input
from pymut4se.model.execution_environment import ExecutionEnvironment
from pymut4se.model.execution_output import ExecutionOutput


class Execution(ABC):
    """
    The Execution class defines the interface for executing code chunks in a specified environment and mode.
    """
    @abstractmethod
    def _run_execution(
        self, code: CodeChunk, execution_input: Input, environment: ExecutionEnvironment
    ) -> ExecutionOutput:
        pass
