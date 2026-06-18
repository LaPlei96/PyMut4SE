import uuid
import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict

from pymut4se.execution.execution_engine import ExecutionEngine
from pymut4se.model.code_chunk import CodeChunk
from pymut4se.model.execution_environment import ExecutionEnvironment, ExecutionEnvironmentType
from pymut4se.model.input import Input, ProgramInput
from pymut4se.mutations.python.standard.arithmetic_mutation import ArithmeticMutation
from pymut4se.mutations.python.standard.assignments_mutation import AssignmentMutation
from pymut4se.mutations.python.standard.comparision_mutation import ComparisionMutation
from pymut4se.mutations.python.standard.delete_general_stmt_mutation import DeleteMutation
from pymut4se.mutations.python.standard.add_if_not_null import IfNotNullMutation
from pymut4se.mutations.python.standard.type_cast_mutation import TypeCastMutation
from pymut4se.mutations.python.standard.optional_param_mutation import OptionalParamMutation
from pymut4se.mutations.python.standard.unary_mutation import UnaryMutation
from pymut4se.mutations.python.standard.constant_mutation import ConstantMutation
from loguru import logger

import sqlite3

MUTATION_OPERATORS = {
    "ArithmeticMutation": ArithmeticMutation,
    "AssignmentMutation": AssignmentMutation,
    "ComparisionMutation": ComparisionMutation,
    "DeleteMutation": DeleteMutation,
    "IfNotNullMutation": IfNotNullMutation,
    "TypeCastMutation": TypeCastMutation,
    "OptionalParamMutation": OptionalParamMutation,
    "UnaryMutation": UnaryMutation,
    "ConstantMutation": ConstantMutation
}

def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
    
def db_open_connection(dbname: str):
    conn = sqlite3.connect(dbname)
    cursor = conn.cursor()
    return cursor, conn

def db_close_connection(conn):
    conn.commit()
    conn.close()

def get_input_json(location: Path) -> list[ProgramInput]:
    with open(location, "r") as f:
        data = json.load(f)
        return [ProgramInput(**item) for item in data]


def get_inputs_jsonl(location: Path) -> list[ProgramInput]:
    inputs = []
    with open(location, "r") as file:
        for line in file:
            testcase = json.loads(line)
            inp,out = testcase
            inputs.append(ProgramInput("text",inp,str(inp)))
    logger.info(f"Loaded {len(inputs)} inputs from {location}") 
    return inputs

def build_inputs(cfg: dict, cursor) -> List[Input]:
    exec_cfg = cfg.get("execution", {})
    mode = exec_cfg.get("mode", "standalone")
    if cfg.get("inputs_file"):
        input_file = Path(cfg["inputs_file"])
        if input_file.suffix == ".json":
            inputs = get_input_json(input_file)
        elif input_file.suffix == ".jsonl":
            inputs = get_inputs_jsonl(Path(cfg["inputs_file"]))
    else:
        inputs_cfg = cfg.get("inputs", []) or [{}]

    build_inps: List[Input] = []
    if inputs != []:
        for item in inputs:
            build_inps.append(
                Input(
                    type=item.type,
                    value={"args": item.value, "representation": item.text_representation},
                    function_name=cfg["function_name"],
                    mode=mode,
                    code_location=Path(cfg["file_path"]),
                    working_dir=Path(exec_cfg["working_dir"]) if exec_cfg.get("working_dir") else None,
                    test_command=exec_cfg.get("test_command"),
                    timeout_seconds=exec_cfg.get("timeout_seconds", 2),
                    extra_env=exec_cfg.get("extra_env"),
                    requirements_path=Path(exec_cfg["requirements_path"]) if exec_cfg.get("requirements_path") else None,
                )
            )
    elif inputs_cfg != []:
        for item in inputs_cfg:
            payload = {"args": item.get("args", []), "kwargs": item.get("kwargs", {})}
            build_inps.append(
                Input(
                    type="args",
                    value=payload,
                    function_name=cfg["function_name"],
                    mode=mode,
                    code_location=Path(cfg["file_path"]),
                    working_dir=Path(exec_cfg["working_dir"]) if exec_cfg.get("working_dir") else None,
                    test_command=exec_cfg.get("test_command"),
                    timeout_seconds=exec_cfg.get("timeout_seconds", 2),
                    extra_env=exec_cfg.get("extra_env"),
                    requirements_path=Path(exec_cfg["requirements_path"]) if exec_cfg.get("requirements_path") else None,
                )
            )
    
    changed_inputs = [
            {**vars(row), "input_id": str(row.input_id), "value":str(row.value), "code_location": str(row.code_location), "working_dir": str(row.working_dir), "test_command": str(row.test_command), "extra_env": str(row.extra_env), "requirements_path": str(row.requirements_path)}
            for row in build_inps
        ]
    for i, inp in enumerate(changed_inputs):
        cursor.execute(
            "SELECT input_id FROM input WHERE type = :type AND value = :value AND function_name = :function_name",
            inp
        )
        existing = cursor.fetchone()
        if existing:
            inp['input_id'] = existing[0]
            cursor.execute(
                "UPDATE input SET type = :type, value = :value, function_name = :function_name, mode = :mode, code_location = :code_location, working_dir = :working_dir, test_command = :test_command, timeout_seconds = :timeout_seconds, extra_env = :extra_env, requirements_path = :requirements_path WHERE input_id = :input_id",
                inp
            )
        else:
            cursor.execute(
                "INSERT INTO input (input_id, type, value, function_name, mode, code_location, working_dir, test_command, timeout_seconds, extra_env, requirements_path) VALUES (:input_id, :type, :value, :function_name, :mode, :code_location, :working_dir, :test_command, :timeout_seconds, :extra_env, :requirements_path)",
                inp
            )
        build_inps[i].input_id = uuid.UUID(inp['input_id'],version=4)
    cursor.connection.commit()
    return build_inps

    

def gen_mutants(codelocation : Path,  operator_names: List[str], cursor,function_name,order:int=1):    
    with open(codelocation, "r") as file:
        code_str = file.read()
    base_chunk = CodeChunk(code_str, "python", function_name, location=codelocation)
    base_chunk.original_code = base_chunk.chunk_id
    changed_base_chunk = {**vars(base_chunk), "chunk_id": str(base_chunk.chunk_id), "location": str(base_chunk.location), "original_code": str(base_chunk.original_code), "parent_id": str(base_chunk.parent_id)}
    cursor.execute(
        "INSERT OR IGNORE INTO code_chunk (chunk_id, code, pl, function_name, mutation_degree, location, original_code, parent_id, line_changed, mutation_type, mutation_operator, mutation_tool) VALUES (:chunk_id, :code, :pl, :function_name, :mutation_degree, :location, :original_code, :parent_id, :line_changed, :mutation_type, :mutation_operator, :mutation_tool)",
        changed_base_chunk
    )
    degree=0
    list_of_mutants = [[base_chunk]]
    logger.info(f"Generating mutants of degree {degree+1}...")
    while degree<order:
        mutants_of_degree = []
        for chunk in list_of_mutants[degree]:
            _, mutants = generate_and_store_mutants(chunk, operator_names, cursor)
            mutants_of_degree.extend(mutants)
        degree+=1
        
        mutant_set = set()
        final_mutants_degree = []
        for mutant in mutants_of_degree:
            if mutant.chunk_id not in mutant_set:
                mutant_set.add(mutant.chunk_id)
                final_mutants_degree.append(mutant)

        list_of_mutants.append(final_mutants_degree)
        logger.info(f"Generated {len(final_mutants_degree)} mutants of degree {degree}.")
    return base_chunk, list_of_mutants



def generate_and_store_mutants(base_chunk, operator_names, cursor):
    mutants: List[CodeChunk] = []

    for name in operator_names:
        op_cls = MUTATION_OPERATORS.get(name)
        if not op_cls:
            print(f"Unknown operator '{name}', skipping.")
            continue
        op = op_cls()
        parsed = op._parse(base_chunk)
        points = op._find_mutation_points(parsed)
        results = []
        for mutant in op._apply_mutation(base_chunk, parsed, points):
            try:
                op._parse(mutant)
                results.append(mutant)
            except Exception:
                continue
        mutants.extend(results)


    changed_mutants = [
        {**vars(row), "chunk_id": str(row.chunk_id), "location": str(row.location), "original_code": str(row.original_code), "parent_id": str(row.parent_id)}
        for row in mutants
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO code_chunk (chunk_id, code, pl, function_name, mutation_degree, location, original_code, parent_id, line_changed, mutation_type, mutation_operator, mutation_tool) VALUES (:chunk_id, :code, :pl, :function_name, :mutation_degree, :location, :original_code, :parent_id, :line_changed, :mutation_type, :mutation_operator, :mutation_tool)",
        changed_mutants
    )
    cursor.connection.commit()    
    return base_chunk, mutants



def build_environment(exec_cfg: dict, cursor) -> ExecutionEnvironment:
    mode = exec_cfg.get("mode", "standalone")
    env_type = ExecutionEnvironmentType.CONTAINER if mode == "project-container" else ExecutionEnvironmentType.LOCAL
    ex_env = ExecutionEnvironment(
        name=f"{env_type.value}-{exec_cfg.get('python_executable') or 'default'}",
        type=env_type,
        version=str(exec_cfg.get("python_executable") or exec_cfg.get("version") or "local"),
        os="unknown",
        version_details={},
        python_executable=exec_cfg.get("python_executable"),
        container_image=exec_cfg.get("container_image"),
    )

    changed_env = {**vars(ex_env), "type": str(ex_env.type), "version_details": str(ex_env.version_details), "environment_id": str(ex_env.environment_id)}
    cursor.execute(
        "SELECT environment_id FROM execution_environment WHERE name = :name AND type = :type",
        changed_env
    )
    existing = cursor.fetchone()
    if existing:
        ex_env.environment_id = uuid.UUID(existing[0])
    else:
        cursor.execute("INSERT INTO execution_environment (name, type, version, os, version_details, python_executable, container_image, environment_id) VALUES (:name, :type, :version, :os, :version_details, :python_executable, :container_image, :environment_id)",
                       changed_env)
    return ex_env

def execute_and_store_output(base_chunk, inp, env, engine, cursor):
    cursor.execute(
        "SELECT COUNT(execution_id) FROM execution_output WHERE code_chunk_id = ? AND input_id = ? AND execution_environment_id = ?",
        (str(base_chunk.chunk_id), str(inp.input_id), str(env.environment_id)),
    )
    if cursor.fetchone()==(0,) :
        output = engine.run(base_chunk, inp, env)
        changed_output = {**vars(output), "execution_id": str(output.execution_id), "output": str(output.output), "success": str(output.success), "code_chunk_id": str(output.code_chunk_id), "execution_environment_id": str(output.execution_environment_id), "input_id": str(output.input_id)}
        cursor.execute(
            "INSERT INTO execution_output (success, output, code_chunk_id, execution_environment_id, input_id, error_message, time_taken, execution_id) VALUES (:success, :output, :code_chunk_id, :execution_environment_id, :input_id, :error_message, :time_taken, :execution_id)",
            changed_output
        )

def main(db_path: str,config_path: Path, mutation_degree :int):
    logger.remove()  # Remove default logger to avoid duplicate logs
    logger.add(sys.stdout, colorize=True, format="<green>{time}</green> <level>{message}</level>")
    cfg = load_config(config_path)
    logger.info(f"Loaded config from {config_path}")
    code_path = Path(cfg["file_path"])
    operator_names = cfg.get("operators", [])
    function_name = cfg.get("function_name")
    logger.info(f"Function name: {function_name}")
    
    if not operator_names:
        # If none provided, apply all known operators that are available
        operator_names = [name for name, cls in MUTATION_OPERATORS.items() if cls]

    logger.info(f"Using mutation operators: {operator_names}")
    cursor, conn = db_open_connection(db_path)

    env = build_environment(cfg.get("execution", {}), cursor)


    inputs = build_inputs(cfg, cursor)
    logger.info(f"Built {len(inputs)} inputs for execution")
    logger.info(f"Execution environment: {env}")

    # for mutation degree 1
    base_chunk, mutants = gen_mutants(code_path, operator_names,cursor,function_name, mutation_degree)
    logger.info(f"Generated mutants: {sum([len(results) for results in mutants])}")

    engine = ExecutionEngine()
    # Get execution output from original code chunk
    logger.info("Executing original code chunk with all inputs...")
    for inp in inputs:
        execute_and_store_output(base_chunk, inp, env, engine, cursor)
    logger.info("Executed original code chunk with all inputs and stored outputs.")

    for i,mutant_degree in enumerate(mutants[1:]):
        logger.info(f"Executing mutants of degree {i+1}, total mutants of this degree: {len(mutant_degree)}")
        logger.info(f"Percentage of Completion: {i}/{len(mutants)-1} ({((i)/(len(mutants)-1))*100:.2f}%)")

        for j,mutant in enumerate(mutant_degree):
            logger.info(f"Executing mutant {j+1}/{len(mutant_degree)} of degree {i+1}, ({(((i)/(len(mutants)-1))+(((j+1)/len(mutant_degree))*(1/(len(mutants)-1))))*100:.2f}%)")
            for inp in inputs:
                execute_and_store_output(mutant, inp, env, engine, cursor)
        cursor.connection.commit()

    db_close_connection(conn)
     

def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run mutation pipeline from a JSON config.\n\nConfig schema:\n"
        "- file_path: path to the Python file to mutate\n"
        "- function_name: target function name (used in inputs)\n"
        "- operators: list of mutation operator names (default: all discovered)\n"
        "- execution: {mode: standalone|project|project-container, python_executable, working_dir, test_command, requirements_path}\n"
        "- inputs: list of {args: [], kwargs: {}} OR inputs_file: path to JSON/JSONL list of inputs\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to JSON config file",
    )
    parser.add_argument(
        "--list-operators",
        action="store_true",
        help="List available operator names and exit",
    )
    parser.add_argument(
        "--degree",
        type=int,
        default=1,
        help="Set the maximal mutation degree (default: 1)",
    )

    parser.add_argument(
        "--db",
        required=True,
        type=str,
        help="Path to db",
    )

    return parser


def list_operators():
    available: Dict[str, object] = {k: v for k, v in MUTATION_OPERATORS.items() if v}
    print("Available mutation operators:")
    for name in sorted(available.keys()):
        print(f"- {name}")


if __name__ == "__main__":
    parser = build_cli_parser()
    args = parser.parse_args()

    if args.list_operators:
        list_operators()
        sys.exit(0)


    main(args.db, args.config, args.degree)

