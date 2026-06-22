from __future__ import annotations

from typing import ClassVar, Optional

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from pymut4se.model.base import Base, generate_id


class TestSuite(Base):
    """Test directory or Python test module.

    Suites form a directory/module hierarchy. A module suite may reference the
    production module that it appears to exercise and contains discovered cases.
    """

    __tablename__ = "test_suites"
    __table_args__ = (CheckConstraint("suite_type IN ('directory', 'module')", name="ck_test_suites_type"),)

    suite_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.project_id"), index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(ForeignKey("test_suites.suite_id"), index=True)
    target_module_id: Mapped[Optional[str]] = mapped_column(ForeignKey("modules.module_id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    suite_type: Mapped[str] = mapped_column(String, nullable=False)
    absolute_path: Mapped[Optional[str]] = mapped_column(String)
    source: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped[Optional[Project]] = relationship(back_populates="test_suites")
    parent: Mapped[Optional[TestSuite]] = relationship(back_populates="children", remote_side="TestSuite.suite_id")
    children: Mapped[list[TestSuite]] = relationship(back_populates="parent")
    target_module: Mapped[Optional[Module]] = relationship()
    test_cases: Mapped[list[TestCase]] = relationship(back_populates="suite")

    def __init__(
        self,
        name: str,
        path: str,
        suite_type: str,
        absolute_path: Optional[str] = None,
        parent_id: Optional[str] = None,
        source: Optional[str] = None,
        target_module_id: Optional[str] = None,
        suite_id: str = "",
        project_id: Optional[str] = None,
    ) -> None:
        if not name:
            msg = "name must not be empty"
            raise ValueError(msg)
        if not path:
            msg = "path must not be empty"
            raise ValueError(msg)
        if suite_type not in {"directory", "module"}:
            msg = "suite_type must be either 'directory' or 'module'"
            raise ValueError(msg)
        if not suite_id:
            identity = f"{parent_id or ''}:{name}:{path}:{suite_type}"
            suite_id = generate_id(identity)
        super().__init__(
            name=name,
            path=path,
            suite_type=suite_type,
            absolute_path=absolute_path,
            parent_id=parent_id,
            source=source,
            target_module_id=target_module_id,
            suite_id=suite_id,
            project_id=project_id,
        )

    @validates("name", "path")
    def validate_required_text(self, key: str, value: str) -> str:
        if not value:
            msg = f"{key} must not be empty"
            raise ValueError(msg)
        return value

    @validates("suite_type")
    def validate_suite_type(self, _key: str, value: str) -> str:
        if value not in {"directory", "module"}:
            msg = "suite_type must be either 'directory' or 'module'"
            raise ValueError(msg)
        return value


class TestCase(Base):
    """Test function or method and its inferred production targets.

    ``targets`` contains association objects describing why and how confidently
    the case is connected to a module or code chunk. Convenience properties expose
    the primary and unique module/chunk objects.
    """

    __tablename__ = "test_cases"

    test_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.project_id"), index=True)
    suite_id: Mapped[str] = mapped_column(ForeignKey("test_suites.suite_id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    start_line: Mapped[Optional[int]]
    end_line: Mapped[Optional[int]]
    code: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped[Optional[Project]] = relationship(back_populates="test_cases")
    suite: Mapped[TestSuite] = relationship(back_populates="test_cases")
    targets: Mapped[list[TestTarget]] = relationship(back_populates="test_case", cascade="all, delete-orphan")
    execution_outputs: Mapped[list[TestExecutionOutput]] = relationship(
        back_populates="test_case",
        cascade="all, delete-orphan",
    )

    def __init__(
        self,
        name: str,
        suite_id: str,
        targets: Optional[list[TestTarget]] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        code: Optional[str] = None,
        test_id: str = "",
        project_id: Optional[str] = None,
    ) -> None:
        if not name:
            msg = "name must not be empty"
            raise ValueError(msg)
        if not suite_id:
            msg = "suite_id must not be empty"
            raise ValueError(msg)
        if not test_id:
            identity = f"{suite_id}:{name}:{start_line or ''}"
            test_id = generate_id(identity)
        super().__init__(
            name=name,
            suite_id=suite_id,
            targets=list(targets or []),
            start_line=start_line,
            end_line=end_line,
            code=code,
            test_id=test_id,
            project_id=project_id,
        )

    @validates("name", "suite_id")
    def validate_required_text(self, key: str, value: str) -> str:
        if not value:
            msg = f"{key} must not be empty"
            raise ValueError(msg)
        return value

    @property
    def target_chunk(self) -> Optional[CodeChunk]:
        """Return the highest-confidence chunk target, if one exists."""
        chunk_targets = [target for target in self.targets if target.chunk is not None]
        if not chunk_targets:
            return None
        return max(chunk_targets, key=lambda target: target.confidence).chunk

    @property
    def target_chunks(self) -> list[CodeChunk]:
        """Return unique chunk targets ordered by descending confidence."""
        return self._unique_target_objects("chunk")

    @property
    def target_module(self) -> Optional[Module]:
        """Return the highest-confidence module target, if one exists."""
        module_targets = [target for target in self.targets if target.module is not None]
        if not module_targets:
            return None
        return max(module_targets, key=lambda target: target.confidence).module

    @property
    def target_modules(self) -> list[Module]:
        """Return unique module targets ordered by descending confidence."""
        return self._unique_target_objects("module")

    def _unique_target_objects(self, attribute: str) -> list:
        objects = []
        seen_ids = set()
        for target in sorted(self.targets, key=lambda item: item.confidence, reverse=True):
            target_object = getattr(target, attribute)
            if target_object is None:
                continue
            identity = getattr(target_object, f"{attribute}_id")
            if identity not in seen_ids:
                seen_ids.add(identity)
                objects.append(target_object)
        return objects


class TestTarget(Base):
    """Evidence-backed association between a test case and production code."""

    __tablename__ = "test_targets"
    __table_args__ = (
        CheckConstraint("module_id IS NOT NULL OR chunk_id IS NOT NULL", name="ck_test_targets_target"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_test_targets_confidence"),
    )

    allowed_evidence: ClassVar[frozenset[str]] = frozenset(
        {"direct_call", "qualified_call", "import", "name_match", "coverage", "manual"}
    )

    target_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    test_id: Mapped[str] = mapped_column(ForeignKey("test_cases.test_id"), index=True)
    module_id: Mapped[Optional[str]] = mapped_column(ForeignKey("modules.module_id"), index=True)
    chunk_id: Mapped[Optional[str]] = mapped_column(ForeignKey("code_chunks.chunk_id"), index=True)
    evidence: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_line: Mapped[Optional[int]] = mapped_column(Integer)

    test_case: Mapped[TestCase] = relationship(back_populates="targets")
    module: Mapped[Optional[Module]] = relationship(back_populates="test_targets")
    chunk: Mapped[Optional[CodeChunk]] = relationship(back_populates="test_targets")

    def __init__(
        self,
        test_id: str,
        evidence: str,
        confidence: float,
        module: Optional[Module] = None,
        chunk: Optional[CodeChunk] = None,
        module_id: Optional[str] = None,
        chunk_id: Optional[str] = None,
        source_line: Optional[int] = None,
        target_id: str = "",
    ) -> None:
        module_id = module.module_id if module is not None else module_id
        chunk_id = chunk.chunk_id if chunk is not None else chunk_id
        if module_id is None and chunk is not None:
            module_id = chunk.module_id
        if module_id is None and chunk_id is None:
            msg = "a test target must reference a module or code chunk"
            raise ValueError(msg)
        if evidence not in self.allowed_evidence:
            msg = f"unsupported target evidence: {evidence}"
            raise ValueError(msg)
        if not 0 <= confidence <= 1:
            msg = "confidence must be between 0 and 1"
            raise ValueError(msg)
        if not target_id:
            identity = f"{test_id}:{module_id or ''}:{chunk_id or ''}:{evidence}:{source_line or ''}"
            target_id = generate_id(identity)
        super().__init__(
            target_id=target_id,
            test_id=test_id,
            module_id=module_id,
            chunk_id=chunk_id,
            evidence=evidence,
            confidence=confidence,
            source_line=source_line,
            module=module,
            chunk=chunk,
        )

    @validates("confidence")
    def validate_confidence(self, _key: str, value: float) -> float:
        if not 0 <= value <= 1:
            msg = "confidence must be between 0 and 1"
            raise ValueError(msg)
        return value

    @validates("evidence")
    def validate_evidence(self, _key: str, value: str) -> str:
        if value not in self.allowed_evidence:
            msg = f"unsupported target evidence: {value}"
            raise ValueError(msg)
        return value


from pymut4se.model.code_chunk import CodeChunk  # noqa: E402
from pymut4se.model.module import Module  # noqa: E402
from pymut4se.model.project import Project  # noqa: E402
from pymut4se.model.execution_test_output import TestExecutionOutput  # noqa: E402
