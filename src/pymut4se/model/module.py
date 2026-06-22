from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from pymut4se.model.base import Base, generate_id


class Module(Base):
    """Python source module and its discovered code chunks.

    ``code_chunks`` contains originals and mutants. ``original_code_chunks`` is
    a read-only filtered relationship containing chunks with mutation degree zero.
    A module may be package-less when exploring a standalone Python file.
    """

    __tablename__ = "modules"

    module_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.project_id"), index=True)
    package_id: Mapped[Optional[str]] = mapped_column(ForeignKey("packages.package_id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped[Optional[Project]] = relationship(back_populates="modules")
    package: Mapped[Optional[Package]] = relationship(back_populates="modules")
    code_chunks: Mapped[list[CodeChunk]] = relationship(back_populates="module")
    original_code_chunks: Mapped[list[CodeChunk]] = relationship(
        primaryjoin="and_(Module.module_id == CodeChunk.module_id, CodeChunk.mutation_degree == 0)",
        viewonly=True,
    )
    test_targets: Mapped[list[TestTarget]] = relationship(back_populates="module")

    def __init__(
        self,
        name: str,
        path: str,
        package_id: Optional[str] = None,
        module_id: str = "",
        source: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        if not name:
            msg = "name must not be empty"
            raise ValueError(msg)
        if not path:
            msg = "path must not be empty"
            raise ValueError(msg)
        if not module_id:
            identity = f"{package_id or ''}:{name}:{path}"
            module_id = generate_id(identity)
        super().__init__(
            name=name,
            path=path,
            package_id=package_id,
            module_id=module_id,
            source=source,
            project_id=project_id,
        )

    @validates("name", "path")
    def validate_required_text(self, key: str, value: str) -> str:
        if not value:
            msg = f"{key} must not be empty"
            raise ValueError(msg)
        return value


from pymut4se.model.code_chunk import CodeChunk  # noqa: E402
from pymut4se.model.package import Package  # noqa: E402
from pymut4se.model.project import Project  # noqa: E402
from pymut4se.model.test import TestTarget  # noqa: E402
