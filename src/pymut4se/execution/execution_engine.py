from pymut4se.execution.python_execution import  StandalonePythonExecution
from pymut4se.model.code_chunk import CodeChunk
from pymut4se.model.execution_environment import ExecutionEnvironment
from pymut4se.model.execution_output import ExecutionOutput
from pymut4se.model.input import Input


class ExecutionEngine:
    """
    The ExecutionEngine is responsible for executing code chunks in a specified environment and mode.
    It currently only supports standalone execution, and will be extended to support additional modes in the future.
    """
    def __init__(self):
        self._standalone = StandalonePythonExecution()

    def run(self, code: CodeChunk, execution_input: Input, environment: ExecutionEnvironment) -> ExecutionOutput:
        """
        Executes the given code chunk in the specified environment and mode.
            :param code: The code chunk to be executed.
            :param execution_input: The input containing the execution mode and any necessary parameters.
            :param environment: The execution environment in which to run the code.
            :return: The output of the execution.
        """
        if execution_input.mode == "standalone":
            runner = self._standalone
            return runner._run_execution(code, execution_input, environment)
        else:
            raise ValueError(f"Unsupported execution mode: {execution_input.mode}")
