import hashlib
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.model import Base, CodeChunk, ExecutionOutput, FunctionInput, Module

ENVIRONMENT_ID = "environment"


def _execution_graph() -> tuple[Module, CodeChunk, CodeChunk, FunctionInput]:
    module = Module("example", "example.py")
    original = CodeChunk(
        "def add(left, right):\n    return left + right\n",
        module.module_id,
        "add",
        "function",
        1,
        2,
    )
    mutant = CodeChunk(
        "def add(left, right):\n    return left - right\n",
        module.module_id,
        "add",
        "function",
        1,
        2,
        mutation_degree=1,
        original_id=original.chunk_id,
        parent_id=original.chunk_id,
    )
    mutant.parent = original
    mutant.original = original
    module.code_chunks.extend([original, mutant])
    function_input = FunctionInput.from_value((2, 1), "add(2, 1)", original_chunk=original)
    return module, original, mutant, function_input


def test_execution_output_connects_a_chunk_and_applicable_input() -> None:
    _, _, mutant, function_input = _execution_graph()
    output = {"result": 1}

    execution = ExecutionOutput(
        success=True,
        output=output,
        code_chunk=mutant,
        function_input=function_input,
        environment_id=ENVIRONMENT_ID,
        time_taken=0.25,
    )

    normalized_output = json.dumps(output, sort_keys=True, separators=(",", ":"))
    identity = f"{mutant.chunk_id}:{function_input.input_id}:{ENVIRONMENT_ID}:True:{normalized_output}::0.25"
    assert execution.execution_id == hashlib.sha256(identity.encode()).hexdigest()
    assert execution.code_chunk is mutant
    assert execution.function_input is function_input
    assert mutant.execution_outputs == [execution]
    assert function_input.execution_outputs == [execution]


def test_execution_identity_changes_with_result_content() -> None:
    _, original, _, function_input = _execution_graph()

    success = ExecutionOutput(
        True,
        {"result": 3},
        original,
        function_input,
        ENVIRONMENT_ID,
        time_taken=0.1,
    )
    failure = ExecutionOutput(
        False,
        None,
        original,
        function_input,
        ENVIRONMENT_ID,
        error_message="boom",
        time_taken=0.1,
    )

    duplicate = ExecutionOutput(
        True,
        {"result": 3},
        original,
        function_input,
        ENVIRONMENT_ID,
        time_taken=0.1,
    )
    assert success.execution_id == duplicate.execution_id
    assert success.execution_id != failure.execution_id


def test_execution_outputs_round_trip_with_relationships() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    module, _, mutant, function_input = _execution_graph()
    execution = ExecutionOutput(
        success=False,
        output={"partial": [1, 2]},
        code_chunk=mutant,
        function_input=function_input,
        environment_id=ENVIRONMENT_ID,
        error_message="assertion failed",
        time_taken=0.5,
    )

    with Session(engine) as session:
        session.add(module)
        session.commit()
        session.expire_all()

        stored = session.get(ExecutionOutput, execution.execution_id)
        assert stored is not None
        assert stored.output == {"partial": [1, 2]}
        assert stored.code_chunk.chunk_id == mutant.chunk_id
        assert stored.function_input.input_id == function_input.input_id
        assert stored in stored.code_chunk.execution_outputs
        assert stored in stored.function_input.execution_outputs


def test_execution_output_validates_input_time_and_json_output() -> None:
    _, original, mutant, function_input = _execution_graph()
    unrelated = CodeChunk(
        "def other():\n    return None\n",
        "other-module",
        "other",
        "function",
        1,
        2,
    )

    with pytest.raises(ValueError, match="time_taken must be greater than or equal to 0"):
        ExecutionOutput(True, None, mutant, function_input, ENVIRONMENT_ID, time_taken=-1)
    with pytest.raises(ValueError, match="output must be JSON serializable"):
        ExecutionOutput(True, {object()}, mutant, function_input, ENVIRONMENT_ID)
    with pytest.raises(ValueError, match="function_input must apply to code_chunk"):
        ExecutionOutput(True, None, unrelated, function_input, ENVIRONMENT_ID)
    with pytest.raises(ValueError, match="environment_id must not be empty"):
        ExecutionOutput(True, None, mutant, function_input, "")

    assert original.execution_outputs == []
