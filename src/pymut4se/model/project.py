from __future__ import annotations

from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from pymut4se.model.base import Base, generate_id


class Project(Base):
    """Root ORM aggregate for an explored Python project.

    A project directly owns the packages, modules, code chunks, test suites, and
    test cases discovered for one filesystem path. Adding a project to a session
    also adds objects reachable through these relationships. Dependency
    specifications are normalized through the ``requirements`` relationship;
    the original manifest path and content remain available as a reproducible
    installation source.
    """

    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    absolute_path: Mapped[Optional[str]] = mapped_column(String)
    requirements_path: Mapped[Optional[str]] = mapped_column(String)
    requirements_content: Mapped[Optional[str]] = mapped_column(Text)

    requirements: Mapped[list[Requirement]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Requirement.position",
    )
    packages: Mapped[list[Package]] = relationship(back_populates="project")
    modules: Mapped[list[Module]] = relationship(back_populates="project")
    code_chunks: Mapped[list[CodeChunk]] = relationship(back_populates="project")
    test_suites: Mapped[list[TestSuite]] = relationship(back_populates="project")
    test_cases: Mapped[list[TestCase]] = relationship(back_populates="project")

    def __init__(
        self,
        name: str,
        path: str,
        absolute_path: Optional[str] = None,
        requirements_path: Optional[str] = None,
        requirements_content: Optional[str] = None,
        requirements: Optional[list[str]] = None,
        packages: Optional[list[Package]] = None,
        modules: Optional[list[Module]] = None,
        code_chunks: Optional[list[CodeChunk]] = None,
        test_suites: Optional[list[TestSuite]] = None,
        test_cases: Optional[list[TestCase]] = None,
        project_id: str = "",
    ) -> None:
        if not name:
            msg = "name must not be empty"
            raise ValueError(msg)
        if not path:
            msg = "path must not be empty"
            raise ValueError(msg)
        if not project_id:
            identity = f"{name}:{path}:{absolute_path or ''}"
            project_id = generate_id(identity)
        requirement_rows = []
        seen_requirements = set()
        for specification in requirements or []:
            if specification in seen_requirements:
                continue
            seen_requirements.add(specification)
            requirement_rows.append(
                Requirement(
                    project_id=project_id,
                    specification=specification,
                    position=len(requirement_rows),
                )
            )
        super().__init__(
            name=name,
            path=path,
            absolute_path=absolute_path,
            requirements_path=requirements_path,
            requirements_content=requirements_content,
            requirements=requirement_rows,
            packages=list(packages or []),
            modules=list(modules or []),
            code_chunks=list(code_chunks or []),
            test_suites=list(test_suites or []),
            test_cases=list(test_cases or []),
            project_id=project_id,
        )

    @validates("name", "path")
    def validate_required_text(self, key: str, value: str) -> str:
        if not value:
            msg = f"{key} must not be empty"
            raise ValueError(msg)
        return value

    @property
    def package_count(self) -> int:
        return len(self.packages)

    @property
    def module_count(self) -> int:
        return len(self.modules)

    @property
    def code_chunk_count(self) -> int:
        return len(self.code_chunks)

    @property
    def test_suite_count(self) -> int:
        return len(self.test_suites)

    @property
    def test_case_count(self) -> int:
        return len(self.test_cases)

    @property
    def requirement_count(self) -> int:
        return len(self.requirements)

    def get_requirement_strings(self) -> list[str]:
        """Return dependency specifications suitable for installer fallback."""
        return [requirement.specification for requirement in self.requirements]


from pymut4se.model.code_chunk import CodeChunk  # noqa: E402
from pymut4se.model.module import Module  # noqa: E402
from pymut4se.model.package import Package  # noqa: E402
from pymut4se.model.requirement import Requirement  # noqa: E402
from pymut4se.model.test import TestCase, TestSuite  # noqa: E402
