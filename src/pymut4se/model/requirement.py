from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from pymut4se.model.base import Base, generate_id


class Requirement(Base):
    """One normalized dependency specification discovered for a project."""

    __tablename__ = "requirements"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_requirements_position"),
        UniqueConstraint("project_id", "specification", name="uq_requirements_project_specification"),
    )

    requirement_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), index=True)
    specification: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project: Mapped[Project] = relationship(back_populates="requirements")

    def __init__(
        self,
        project_id: str,
        specification: str,
        position: int = 0,
        requirement_id: str = "",
    ) -> None:
        if not project_id:
            msg = "project_id must not be empty"
            raise ValueError(msg)
        if not specification:
            msg = "specification must not be empty"
            raise ValueError(msg)
        if position < 0:
            msg = "position must be greater than or equal to 0"
            raise ValueError(msg)
        if not requirement_id:
            requirement_id = generate_id(f"{project_id}:{specification}")
        super().__init__(
            requirement_id=requirement_id,
            project_id=project_id,
            specification=specification,
            position=position,
        )

    @validates("project_id", "specification")
    def validate_required_text(self, key: str, value: str) -> str:
        if not value:
            msg = f"{key} must not be empty"
            raise ValueError(msg)
        return value

    @validates("position")
    def validate_position(self, _key: str, value: int) -> int:
        if value < 0:
            msg = "position must be greater than or equal to 0"
            raise ValueError(msg)
        return value


from pymut4se.model.project import Project  # noqa: E402
