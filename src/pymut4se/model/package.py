from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from pymut4se.model.base import Base, generate_id


class Package(Base):
    """Python package directory in an explored project.

    Packages form a self-referential tree through ``parent`` and ``children``.
    Python modules directly contained by the package are available through
    ``modules``.
    """

    __tablename__ = "packages"

    package_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.project_id"), index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(ForeignKey("packages.package_id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    absolute_path: Mapped[Optional[str]] = mapped_column(String)

    project: Mapped[Optional[Project]] = relationship(back_populates="packages")
    parent: Mapped[Optional[Package]] = relationship(back_populates="children", remote_side="Package.package_id")
    children: Mapped[list[Package]] = relationship(back_populates="parent")
    modules: Mapped[list[Module]] = relationship(back_populates="package")

    def __init__(
        self,
        name: str,
        path: str,
        absolute_path: Optional[str] = None,
        parent_id: Optional[str] = None,
        package_id: str = "",
        project_id: Optional[str] = None,
    ) -> None:
        if not name:
            msg = "name must not be empty"
            raise ValueError(msg)
        if not path:
            msg = "path must not be empty"
            raise ValueError(msg)
        if not package_id:
            identity = f"{parent_id or ''}:{name}:{path}"
            package_id = generate_id(identity)
        super().__init__(
            name=name,
            path=path,
            absolute_path=absolute_path,
            parent_id=parent_id,
            package_id=package_id,
            project_id=project_id,
        )

    @validates("name", "path")
    def validate_required_text(self, key: str, value: str) -> str:
        if not value:
            msg = f"{key} must not be empty"
            raise ValueError(msg)
        return value


from pymut4se.model.module import Module  # noqa: E402
from pymut4se.model.project import Project  # noqa: E402
