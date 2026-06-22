from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, CheckConstraint, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from pymut4se.model.base import Base, generate_id


class TestExecutionOutput(Base):
    """The persisted result of running one related test against one code chunk."""

    __tablename__ = "test_execution_outputs"
    __table_args__ = (
        CheckConstraint("time_taken >= 0", name="ck_test_execution_outputs_time_taken"),
        UniqueConstraint(
            "code_chunk_id",
            "test_id",
            "environment_id",
            name="uq_test_execution_outputs_chunk_test_environment",
        ),
    )

    execution_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code_chunk_id: Mapped[str] = mapped_column(ForeignKey("code_chunks.chunk_id"), index=True, nullable=False)
    test_id: Mapped[str] = mapped_column(ForeignKey("test_cases.test_id"), index=True, nullable=False)
    environment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    output: Mapped[Any] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    return_code: Mapped[Optional[int]] = mapped_column(Integer)
    time_taken: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    code_chunk: Mapped[CodeChunk] = relationship(back_populates="test_execution_outputs")
    test_case: Mapped[TestCase] = relationship(back_populates="execution_outputs")

    def __init__(
        self,
        success: bool,
        output: Any,
        code_chunk: CodeChunk,
        test_case: TestCase,
        environment_id: str,
        error_message: str = "",
        return_code: Optional[int] = None,
        time_taken: float = 0.0,
        execution_id: str = "",
    ) -> None:
        if time_taken < 0:
            msg = "time_taken must be greater than or equal to 0"
            raise ValueError(msg)
        if not environment_id:
            msg = "environment_id must not be empty"
            raise ValueError(msg)
        if test_case not in code_chunk.related_test_cases:
            msg = "test_case must be related to code_chunk"
            raise ValueError(msg)
        try:
            normalized_output = json.dumps(output, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            msg = "output must be JSON serializable"
            raise ValueError(msg) from error
        if not execution_id:
            identity = (
                f"{code_chunk.chunk_id}:{test_case.test_id}:{environment_id}:{success}:"
                f"{normalized_output}:{error_message}:{return_code}:{time_taken}"
            )
            execution_id = generate_id(identity)
        super().__init__(
            execution_id=execution_id,
            code_chunk_id=code_chunk.chunk_id,
            test_id=test_case.test_id,
            environment_id=environment_id,
            success=success,
            output=output,
            error_message=error_message,
            return_code=return_code,
            time_taken=time_taken,
            code_chunk=code_chunk,
            test_case=test_case,
        )

    @validates("time_taken")
    def validate_time_taken(self, _key: str, value: float) -> float:
        if value < 0:
            msg = "time_taken must be greater than or equal to 0"
            raise ValueError(msg)
        return value


from pymut4se.model.code_chunk import CodeChunk  # noqa: E402
from pymut4se.model.test import TestCase  # noqa: E402
