import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


from pymut4se.execution.execution import Execution
from pymut4se.model.code_chunk import CodeChunk
from pymut4se.model.execution_environment import ExecutionEnvironment
from pymut4se.model.execution_output import ExecutionOutput
from pymut4se.model.input import Input


def _python_exec(environment: ExecutionEnvironment) -> str:
    """
    Helper function to determine the Python executable to use based on the execution environment.
    :param environment: The execution environment containing configuration for the Python executable.
    :return: The path to the Python executable to use for execution.
    """
    return environment.python_executable or sys.executable


class StandalonePythonExecution(Execution):
    """
    A class for executing code chunks in a standalone Python environment.
    """
    def _run_execution(
        self, code: CodeChunk, execution_input: Input, environment: ExecutionEnvironment
    ) -> ExecutionOutput:
        python_bin: str   = _python_exec(environment)
            
        payload = execution_input.value or {"args": [], "kwargs": {}}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path: Path = Path(tmpdir) / "mutant_module.py"
            harness: str = self._build_harness(execution_input.function_name,execution_input.type)
            tmp_path.write_text(data=code.code + "\n\n" + harness, encoding="utf-8")

            try:
                result = subprocess.run(
                    args=[python_bin, str(tmp_path)],
                    input=json.dumps(payload),
                    text=True,
                    capture_output=True,
                    timeout=execution_input.timeout_seconds or 2,
                    env=self._build_env(execution_input),
                )
                success = result.returncode == 0
                output = result.stdout.strip()
                error = None if success else result.stderr
            except Exception as exc: 
                success = False
                output = ""
                error = str(exc)
        exec_output = ExecutionOutput(
            success=success,
            output=output,
            error_message=error or "",
            code_chunk_id=code.chunk_id,
            execution_environment_id=environment.environment_id,
            input_id=execution_input.input_id,
        )
        return exec_output

    def _build_env(self, execution_input: Input) -> dict:
        """Builds the environment variables for the subprocess execution, incorporating any extra environment variables specified in the execution input.
            :param execution_input: The input containing any extra environment variables to include.
            :return: A dictionary of environment variables to use for the subprocess execution.
        """
        env = os.environ.copy()
        if execution_input.extra_env:
            env.update({k: str(v) for k, v in execution_input.extra_env.items()})
        return env

    def _build_harness(self, function_name: str, mode: str) -> str:
        """Builds the harness code for executing the function.
        :param function_name: The name of the function to execute.
        :param mode: The mode of execution ("text" or "binary").
        :return: The harness code as a string.
        """
        if mode == "text":
            return f"""
if __name__ == "__main__":
    import json, sys
    payload = json.loads(sys.stdin.read() or "{{}}")
    args = payload.get("args", [])
    kwargs = payload.get("kwargs", {{}});
    result = globals()["{function_name}"](*args, **kwargs)
    print(json.dumps({{"result": result}}, default=str))
"""
        else:
            return f"""
if __name__ == "__main__":
    import json, sys
    import pickle, base64
    payload = json.loads(sys.stdin.read() or "{{}}")
    payload_value = payload.get("args", "")
    decoded_value = pickle.loads(base64.b64decode(payload_value)) if payload_value else ()
    kwargs = payload.get("kwargs", {{}});
    result = globals()["{function_name}"](*decoded_value, **kwargs)
    print(json.dumps({{"result": result}}, default=str))
"""
