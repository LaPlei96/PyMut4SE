import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.model import Base, CodeChunk, FunctionInput, Module


def _chunk_graph() -> tuple[Module, CodeChunk, CodeChunk]:
    module = Module("example", "example.py")
    original = CodeChunk(
        "def read(start, end):\n    return start, end\n",
        module.module_id,
        "read",
        "function",
        1,
        2,
    )
    mutant = CodeChunk(
        "def read(start, end):\n    return end, start\n",
        module.module_id,
        "read",
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
    return module, original, mutant


def test_serialized_input_applies_to_an_original_and_all_its_mutants() -> None:
    _, original, mutant = _chunk_graph()

    function_input = FunctionInput.from_value(
        (1, 5),
        "read(1, 5)",
        original_chunk=original,
    )

    expected_identity = f"{original.chunk_id}:serialized:{function_input.value}"
    assert function_input.input_id == hashlib.sha256(expected_identity.encode()).hexdigest()
    assert function_input.type == "serialized"
    assert function_input.deserialize_value() == (1, 5)
    assert function_input.function_name == "read"
    assert original.inputs == [function_input]
    assert original.applicable_inputs == [function_input]
    assert mutant.inputs == []
    assert mutant.applicable_inputs == [function_input]
    assert function_input.target_chunks == [original, mutant]


def test_text_input_preserves_its_readable_and_execution_values() -> None:
    _, original, _ = _chunk_graph()

    function_input = FunctionInput.from_text_representation(
        '{"args": [1, 5]}',
        original_chunk=original,
    )

    assert function_input.type == "text"
    assert function_input.value == '{"args": [1, 5]}'
    assert function_input.text_representation == '{"args": [1, 5]}'
    with pytest.raises(ValueError, match="only serialized inputs can be deserialized"):
        function_input.deserialize_value()


def test_input_identity_uses_owner_type_and_value() -> None:
    _, original, _ = _chunk_graph()
    another_original = CodeChunk(
        original.code,
        "another-module",
        "read",
        "function",
        1,
        2,
    )

    first = FunctionInput("text", "payload", original_chunk=original)
    duplicate = FunctionInput("text", "payload", original_chunk_id=original.chunk_id)
    other_type = FunctionInput("serialized", "payload", original_chunk=original)
    other_owner = FunctionInput("text", "payload", original_chunk=another_original)

    assert first.input_id == duplicate.input_id
    assert len({first.input_id, other_type.input_id, other_owner.input_id}) == 3


def test_function_inputs_round_trip_with_the_chunk_graph() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    module, original, mutant = _chunk_graph()
    function_input = FunctionInput.from_value(("start", "end"), "read('start', 'end')", original_chunk=original)

    with Session(engine) as session:
        session.add(module)
        session.commit()
        session.expire_all()

        stored_input = session.get(FunctionInput, function_input.input_id)
        stored_mutant = session.get(CodeChunk, mutant.chunk_id)
        assert stored_input is not None
        assert stored_mutant is not None
        assert stored_input.original_chunk.chunk_id == original.chunk_id
        assert stored_input.deserialize_value() == ("start", "end")
        assert stored_mutant.applicable_inputs == [stored_input]
        assert [chunk.chunk_id for chunk in stored_input.target_chunks] == [
            original.chunk_id,
            mutant.chunk_id,
        ]


def test_function_input_requires_a_supported_type_and_original_chunk() -> None:
    _, original, mutant = _chunk_graph()

    with pytest.raises(ValueError, match="type must be one of"):
        FunctionInput("binary", "payload", original_chunk=original)
    with pytest.raises(ValueError, match="original_chunk_id must not be empty"):
        FunctionInput("text", "payload")
    with pytest.raises(ValueError, match="degree-zero code chunk"):
        FunctionInput("text", "payload", original_chunk=mutant)
