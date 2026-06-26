from __future__ import annotations

from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from pymut4se.model.base import Base, generate_id


class CodeChunk(Base):
    """Function-sized Python source and optional mutation metadata.

    Mutation generations form a tree through ``parent`` and ``children``. Every
    mutant also links directly to its degree-zero ``original`` chunk. Degree-zero
    chunks have no original. Source line numbers are one-based and inclusive.
    """

    __tablename__ = "code_chunks"
    __table_args__ = (
        CheckConstraint("start_line >= 1", name="ck_code_chunks_start_line"),
        CheckConstraint("end_line >= start_line", name="ck_code_chunks_line_range"),
        CheckConstraint("mutation_degree >= 0", name="ck_code_chunks_mutation_degree"),
        CheckConstraint(
            "(mutation_degree = 0 AND original_id IS NULL) OR (mutation_degree > 0 AND original_id IS NOT NULL)",
            name="ck_code_chunks_original",
        ),
    )

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.project_id"), index=True)
    module_id: Mapped[str] = mapped_column(ForeignKey("modules.module_id"), index=True)
    function_name: Mapped[str] = mapped_column(String, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    mutation_degree: Mapped[int] = mapped_column(Integer, default=0)
    original_id: Mapped[Optional[str]] = mapped_column(ForeignKey("code_chunks.chunk_id"), index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(ForeignKey("code_chunks.chunk_id"), index=True)
    line_changed: Mapped[Optional[int]] = mapped_column(Integer)
    column_changed: Mapped[Optional[int]] = mapped_column(Integer)
    mutation_type: Mapped[Optional[str]] = mapped_column(String)
    mutation_operator: Mapped[Optional[str]] = mapped_column(String)

    project: Mapped[Optional[Project]] = relationship(back_populates="code_chunks")
    module: Mapped[Module] = relationship(back_populates="code_chunks")
    parent: Mapped[Optional[CodeChunk]] = relationship(
        back_populates="children",
        foreign_keys="CodeChunk.parent_id",
        remote_side="CodeChunk.chunk_id",
    )
    children: Mapped[list[CodeChunk]] = relationship(back_populates="parent", foreign_keys="CodeChunk.parent_id")
    original: Mapped[Optional[CodeChunk]] = relationship(
        back_populates="derived_chunks",
        foreign_keys="CodeChunk.original_id",
        remote_side="CodeChunk.chunk_id",
    )
    derived_chunks: Mapped[list[CodeChunk]] = relationship(
        back_populates="original", foreign_keys="CodeChunk.original_id"
    )
    test_targets: Mapped[list[TestTarget]] = relationship(back_populates="chunk")
    inputs: Mapped[list[FunctionInput]] = relationship(
        back_populates="original_chunk",
        cascade="all, delete-orphan",
    )
    execution_outputs: Mapped[list[ExecutionOutput]] = relationship(
        back_populates="code_chunk",
        cascade="all, delete-orphan",
    )
    test_execution_outputs: Mapped[list[TestExecutionOutput]] = relationship(
        back_populates="code_chunk",
        cascade="all, delete-orphan",
    )

    def __init__(
        self,
        code: str,
        module_id: str,
        function_name: str,
        chunk_type: str,
        start_line: int,
        end_line: int,
        mutation_degree: int = 0,
        original_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        line_changed: Optional[int] = None,
        column_changed: Optional[int] = None,
        mutation_type: Optional[str] = None,
        mutation_operator: Optional[str] = None,
        chunk_id: str = "",
        project_id: Optional[str] = None,
    ) -> None:
        if start_line < 1:
            msg = "start_line must be greater than or equal to 1"
            raise ValueError(msg)
        if end_line < start_line:
            msg = "end_line must be greater than or equal to start_line"
            raise ValueError(msg)
        if mutation_degree < 0:
            msg = "mutation_degree must be greater than or equal to 0"
            raise ValueError(msg)
        if not function_name:
            msg = "function_name must not be empty"
            raise ValueError(msg)
        if mutation_degree == 0 and original_id is not None:
            msg = "a degree-zero code chunk must not reference an original"
            raise ValueError(msg)
        if mutation_degree > 0 and original_id is None:
            msg = "a mutated code chunk must reference its degree-zero original"
            raise ValueError(msg)
        if not chunk_id:
            identity = f"{module_id}:{function_name}:{chunk_type}:{start_line}:{end_line}:{code}"
            chunk_id = generate_id(identity)
        super().__init__(
            code=code,
            module_id=module_id,
            function_name=function_name,
            chunk_type=chunk_type,
            start_line=start_line,
            end_line=end_line,
            mutation_degree=mutation_degree,
            original_id=original_id,
            parent_id=parent_id,
            line_changed=line_changed,
            column_changed=column_changed,
            mutation_type=mutation_type,
            mutation_operator=mutation_operator,
            chunk_id=chunk_id,
            project_id=project_id,
        )

    @validates("start_line")
    def validate_start_line(self, _key: str, value: int) -> int:
        if value < 1:
            msg = "start_line must be greater than or equal to 1"
            raise ValueError(msg)
        return value

    @validates("mutation_degree")
    def validate_mutation_degree(self, _key: str, value: int) -> int:
        if value < 0:
            msg = "mutation_degree must be greater than or equal to 0"
            raise ValueError(msg)
        return value

    @property
    def applicable_inputs(self) -> list[FunctionInput]:
        """Return inputs owned by this chunk's degree-zero ancestor."""
        if self.mutation_degree == 0:
            return self.inputs
        if self.original is None:
            return []
        return self.original.inputs

    @property
    def related_test_cases(self) -> list[TestCase]:
        """Return unique tests related to this chunk's degree-zero ancestor."""
        source = self if self.mutation_degree == 0 else self.original
        if source is None:
            return []
        return list({target.test_case.test_id: target.test_case for target in source.test_targets}.values())


from pymut4se.model.module import Module  # noqa: E402
from pymut4se.model.input import FunctionInput  # noqa: E402
from pymut4se.model.execution_output import ExecutionOutput  # noqa: E402
from pymut4se.model.execution_test_output import TestExecutionOutput  # noqa: E402
from pymut4se.model.project import Project  # noqa: E402
from pymut4se.model.test import TestCase, TestTarget  # noqa: E402
