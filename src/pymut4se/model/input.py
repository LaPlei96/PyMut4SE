from __future__ import annotations

import base64
import pickle  # nosec B403
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from pymut4se.model.base import Base, generate_id

INPUT_TYPES = {"serialized", "text"}


class FunctionInput(Base):
    """A reusable predetermined input owned by a degree-zero code chunk."""

    __tablename__ = "function_inputs"
    __table_args__ = (CheckConstraint("type IN ('serialized', 'text')", name="ck_function_inputs_type"),)

    input_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    original_chunk_id: Mapped[str] = mapped_column(ForeignKey("code_chunks.chunk_id"), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    text_representation: Mapped[str] = mapped_column(Text, nullable=False, default="")

    original_chunk: Mapped[CodeChunk] = relationship(back_populates="inputs")
    execution_outputs: Mapped[list[ExecutionOutput]] = relationship(
        back_populates="function_input",
        cascade="all, delete-orphan",
    )

    def __init__(
        self,
        type: str,
        value: str,
        original_chunk_id: str = "",
        text_representation: str = "",
        input_id: str = "",
        original_chunk: Optional[CodeChunk] = None,
    ) -> None:
        if type not in INPUT_TYPES:
            msg = f"type must be one of {sorted(INPUT_TYPES)}"
            raise ValueError(msg)
        if original_chunk is not None:
            if original_chunk.mutation_degree != 0:
                msg = "function inputs must belong to a degree-zero code chunk"
                raise ValueError(msg)
            original_chunk_id = original_chunk.chunk_id
        if not original_chunk_id:
            msg = "original_chunk_id must not be empty"
            raise ValueError(msg)
        if not input_id:
            input_id = generate_id(f"{original_chunk_id}:{type}:{value}")
        super().__init__(
            input_id=input_id,
            original_chunk_id=original_chunk_id,
            type=type,
            value=value,
            text_representation=text_representation,
        )
        if original_chunk is not None:
            self.original_chunk = original_chunk

    @classmethod
    def from_value(
        cls,
        value: tuple,
        text_representation: str,
        *,
        original_chunk: CodeChunk,
    ) -> FunctionInput:
        """Create an input whose positional arguments are pickle-encoded."""
        encoded_value = base64.b64encode(pickle.dumps(value)).decode("ascii")
        return cls(
            type="serialized",
            value=encoded_value,
            text_representation=text_representation,
            original_chunk=original_chunk,
        )

    @classmethod
    def from_text_representation(
        cls,
        text_representation: str,
        *,
        original_chunk: CodeChunk,
    ) -> FunctionInput:
        """Create an input whose textual representation is its payload."""
        return cls(
            type="text",
            value=text_representation,
            text_representation=text_representation,
            original_chunk=original_chunk,
        )

    @property
    def function_name(self) -> str:
        """Return the function name through the owning original chunk."""
        return self.original_chunk.function_name

    @property
    def target_chunks(self) -> list[CodeChunk]:
        """Return the original chunk followed by every mutant using this input."""
        return [self.original_chunk, *self.original_chunk.derived_chunks]

    def deserialize_value(self) -> tuple:
        """Decode and return a serialized positional-argument tuple."""
        if self.type != "serialized":
            msg = "only serialized inputs can be deserialized"
            raise ValueError(msg)
        value = pickle.loads(base64.b64decode(self.value))  # noqa: S301  # nosec B301
        if not isinstance(value, tuple):
            msg = "serialized function input must contain a tuple"
            raise ValueError(msg)
        return value

    @validates("type")
    def validate_type(self, _key: str, value: str) -> str:
        if value not in INPUT_TYPES:
            msg = f"type must be one of {sorted(INPUT_TYPES)}"
            raise ValueError(msg)
        return value

    @validates("original_chunk")
    def validate_original_chunk(self, _key: str, value: CodeChunk) -> CodeChunk:
        if value.mutation_degree != 0:
            msg = "function inputs must belong to a degree-zero code chunk"
            raise ValueError(msg)
        return value


from pymut4se.model.code_chunk import CodeChunk  # noqa: E402
from pymut4se.model.execution_output import ExecutionOutput  # noqa: E402
