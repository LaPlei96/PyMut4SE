import argparse
import ast
import json
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any, List, Optional

from loguru import logger

from pymut4se.execution.execution_engine import ExecutionEngine
from pymut4se.model.code_chunk import CodeChunk
from pymut4se.model.execution_environment import (
    ExecutionEnvironment,
    ExecutionEnvironmentType,
)
from pymut4se.model.execution_output import ExecutionOutput
from pymut4se.model.input import Input


def db_open_connection(dbname: str):
    conn = sqlite3.connect(dbname)
    cursor = conn.cursor()
    return cursor, conn


def db_close_connection(conn):
    conn.commit()
    conn.close()


def _none_if_nullish(value: Any) -> Any:
    if value in (None, "None", "null", "NULL", ""):
        return None
    return value


def _to_path_or_none(value: Any) -> Optional[Path]:
    value = _none_if_nullish(value)
    if value is None:
        return None
    return Path(str(value))


def _to_dict_or_none(value: Any) -> Optional[dict]:
    value = _none_if_nullish(value)
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        try:
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None


def _parse_payload(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return {"args": [], "kwargs": {}}

    text = str(value)
    try:
        return json.loads(text)
    except Exception:
        try:
            return ast.literal_eval(text)
        except Exception:
            return {"args": [], "kwargs": {}}


def fetch_inputs_for_function(cursor, function_name: str) -> List[Input]:
    cursor.execute(
        """
        SELECT input_id, type, value, function_name, mode, code_location,
               working_dir, test_command, timeout_seconds, extra_env, requirements_path
        FROM input
        WHERE function_name = ?
        """,
        (function_name,),
    )
    rows = cursor.fetchall()

    inputs: List[Input] = []
    for row in rows:
        (
            input_id,
            input_type,
            value,
            fn,
            mode,
            code_location,
            working_dir,
            test_command,
            timeout_seconds,
            extra_env,
            requirements_path,
        ) = row

        try:
            parsed_input_id = uuid.UUID(str(input_id))
        except Exception:
            parsed_input_id = uuid.uuid4()

        inputs.append(
            Input(
                input_id=parsed_input_id,
                type=input_type or "text",
                value=_parse_payload(value),
                function_name=fn or function_name,
                mode=mode or "standalone",
                code_location=_to_path_or_none(code_location),
                working_dir=_to_path_or_none(working_dir),
                test_command=_none_if_nullish(test_command),
                timeout_seconds=timeout_seconds or 2,
                extra_env=_to_dict_or_none(extra_env),
                requirements_path=_to_path_or_none(requirements_path),
            )
        )

    return inputs


def ensure_environment(cursor, python_executable: Optional[str] = None) -> ExecutionEnvironment:
    env = ExecutionEnvironment(
        name=f"local-{python_executable or 'default'}",
        type=ExecutionEnvironmentType.LOCAL,
        version=str(python_executable or "local"),
        os="unknown",
        version_details={},
        python_executable=python_executable,
    )

    changed_env = {
        **vars(env),
        "type": str(env.type),
        "version_details": str(env.version_details),
        "environment_id": str(env.environment_id),
    }
    cursor.execute(
        "SELECT environment_id FROM execution_environment WHERE name = :name AND type = :type",
        changed_env,
    )
    existing = cursor.fetchone()
    if existing:
        env.environment_id = uuid.UUID(existing[0])
    else:
        cursor.execute(
            """
            INSERT INTO execution_environment
            (name, type, version, os, version_details, python_executable, container_image, environment_id)
            VALUES (:name, :type, :version, :os, :version_details, :python_executable, :container_image, :environment_id)
            """,
            changed_env,
        )
    return env


def ensure_code_chunk(cursor, code_chunk: CodeChunk) -> None:
    logger.debug(f"Ensuring code chunk in DB for function '{code_chunk.function_name}' with chunk_id {code_chunk.chunk_id}")
    changed_chunk = {
        **vars(code_chunk),
        "location": str(code_chunk.location),
        "original_code": str(code_chunk.original_code),
        "parent_id": str(code_chunk.parent_id),
    }
    logger.debug(f"Checking if code chunk with {changed_chunk}")
    cursor.execute(
        """
        INSERT OR IGNORE INTO code_chunk
        (chunk_id, code, pl, function_name, mutation_degree, location, original_code,
         parent_id, line_changed, mutation_type, mutation_operator, mutation_tool)
        VALUES (:chunk_id, :code, :pl, :function_name, :mutation_degree, :location,
                :original_code, :parent_id, :line_changed, :mutation_type,
                :mutation_operator, :mutation_tool)
        """,
        changed_chunk,
    )


def get_root_chunk_id_for_function(cursor, function_name: str) -> Optional[str]:
    cursor.execute(
        """
        SELECT chunk_id
        FROM code_chunk
        WHERE function_name = ? AND mutation_degree = 0
        LIMIT 1
        """,
        (function_name,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def execute_and_store_output(
    code_chunk: CodeChunk,
    inp: Input,
    env: ExecutionEnvironment,
    engine: ExecutionEngine,
    cursor,
) -> Optional[ExecutionOutput]:
    cursor.execute(
        """
        SELECT COUNT(execution_id)
        FROM execution_output
        WHERE code_chunk_id = ? AND input_id = ? AND execution_environment_id = ?
        """,
        (str(code_chunk.chunk_id), str(inp.input_id), str(env.environment_id)),
    )
    if cursor.fetchone() != (0,):
        return None

    output = engine.run(code_chunk, inp, env)
    changed_output = {
        **vars(output),
        "execution_id": str(output.execution_id),
        "output": str(output.output),
        "success": str(output.success),
        "code_chunk_id": str(output.code_chunk_id),
        "execution_environment_id": str(output.execution_environment_id),
        "input_id": str(output.input_id),
    }
    cursor.execute(
        """
        INSERT INTO execution_output
        (success, output, code_chunk_id, execution_environment_id, input_id, error_message, time_taken, execution_id)
        VALUES (:success, :output, :code_chunk_id, :execution_environment_id, :input_id, :error_message, :time_taken, :execution_id)
        """,
        changed_output,
    )
    return output


def execute_code_for_function_inputs(
    code: str,
    function_name: str,
    db_path: str,
    python_executable: Optional[str] = None,
) -> List[ExecutionOutput]:
    cursor, conn = db_open_connection(db_path)
    try:
        code_chunk = CodeChunk(code=code, pl="python", function_name=function_name, mutation_degree=-1,mutation_type="external_input",mutation_operator="none",mutation_tool="none")
        root_chunk_id = get_root_chunk_id_for_function(cursor, function_name)
        if root_chunk_id:
            code_chunk.original_code = root_chunk_id
            code_chunk.parent_id = root_chunk_id
        else:
            code_chunk.original_code = code_chunk.chunk_id
        ensure_code_chunk(cursor, code_chunk)

        env = ensure_environment(cursor, python_executable=python_executable)
        inputs = fetch_inputs_for_function(cursor, function_name)

        if not inputs:
            logger.warning(f"No inputs found in DB for function '{function_name}'.")
            return []

        logger.info(f"Executing {len(inputs)} inputs for function '{function_name}'.")
        engine = ExecutionEngine()
        outputs: List[ExecutionOutput] = []

        for inp in inputs:
            if inp.mode != "standalone":
                logger.warning(
                    f"Skipping input {inp.input_id}: unsupported mode '{inp.mode}' for ExecutionEngine."
                )
                continue
            out = execute_and_store_output(code_chunk, inp, env, engine, cursor)
            if out is not None:
                outputs.append(out)

        conn.commit()
        return outputs
    finally:
        db_close_connection(conn)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute an in-memory Python code string against all DB inputs for a function."
    )
    parser.add_argument("--db", required=True, type=str, help="Path to SQLite DB")
    parser.add_argument("--function-name", required=True, type=str, help="Function name to execute")

    code_group = parser.add_mutually_exclusive_group(required=True)
    code_group.add_argument("--code", type=str, help="Python code as a string")
    code_group.add_argument("--code-file", type=Path, help="Path to file containing Python code")

    parser.add_argument(
        "--python-executable",
        type=str,
        default=None,
        help="Python executable for execution environment (default: current interpreter)",
    )
    return parser


def main() -> None:
    logger.remove()
    logger.add(sys.stdout, colorize=True, format="<green>{time}</green> <level>{message}</level>")

    parser = build_cli_parser()
    args = parser.parse_args()

    code = args.code
    if args.code_file is not None:
        code = args.code_file.read_text(encoding="utf-8")

    outputs = execute_code_for_function_inputs(
        code=code,
        function_name=args.function_name,
        db_path=args.db,
        python_executable=args.python_executable,
    )

    print(json.dumps([vars(o) for o in outputs], default=str, indent=2))


if __name__ == "__main__":
    main()
