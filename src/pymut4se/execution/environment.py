from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pymut4se.model import Project


@dataclass
class PythonExecutionEnvironment:
    """A reusable virtual environment prepared for one explored project."""

    project: Project
    path: Path
    system_python: Path = field(default_factory=lambda: Path(sys.executable))

    @classmethod
    def for_project(
        cls,
        project: Project,
        environments_root: Optional[Path] = None,
    ) -> PythonExecutionEnvironment:
        """Build the conventional reusable environment location for a project."""
        if environments_root is None:
            environments_root = _project_root(project) / ".pymut4se" / "venvs"
        return cls(project=project, path=environments_root / project.project_id)

    @property
    def python_executable(self) -> Path:
        """Return the environment's platform-specific Python executable."""
        if sys.platform == "win32":
            return self.path / "Scripts" / "python.exe"
        return self.path / "bin" / "python"

    @property
    def is_prepared(self) -> bool:
        """Return whether the virtual environment contains a Python executable."""
        return self.python_executable.is_file()

    @property
    def environment_id(self) -> str:
        """Return a stable identity for this project, interpreter, path, and dependencies."""
        identity = json.dumps(
            {
                "path": str(self.path.expanduser().resolve()),
                "project_id": self.project.project_id,
                "requirements": self._requirements_fingerprint(),
                "system_python": str(self.system_python.expanduser().resolve()),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(identity.encode()).hexdigest()

    @property
    def is_current(self) -> bool:
        """Return whether installed requirements match the project's fingerprint."""
        marker = self.path / ".pymut4se-requirements"
        if marker.is_file():
            return marker.read_text(encoding="utf-8") == self._requirements_fingerprint()
        return not (self.project.requirements_path or self.project.requirements_content or self.project.requirements)

    def prepare(self, *, refresh_requirements: bool = False) -> PythonExecutionEnvironment:
        """Create the venv and install requirements when its fingerprint changed."""
        if not self.is_prepared:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [str(self.system_python), "-m", "venv", str(self.path)],
                check=True,
            )
            if not self.is_prepared:
                msg = f"virtual environment did not create a Python executable: {self.python_executable}"
                raise RuntimeError(msg)

        fingerprint = self._requirements_fingerprint()
        marker = self.path / ".pymut4se-requirements"
        installed_fingerprint = marker.read_text(encoding="utf-8") if marker.is_file() else ""
        if refresh_requirements or installed_fingerprint != fingerprint:
            self._install_requirements()
            marker.write_text(fingerprint, encoding="utf-8")
        return self

    def _install_requirements(self) -> None:
        requirement_path = Path(self.project.requirements_path) if self.project.requirements_path else None
        base_command = [
            str(self.python_executable),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
        ]
        if requirement_path is not None and requirement_path.is_file() and requirement_path.suffix.lower() == ".txt":
            subprocess.run([*base_command, "-r", str(requirement_path)], check=True)
        else:
            requirements = self.project.get_requirement_strings()
            if requirements:
                subprocess.run([*base_command, *requirements], check=True)
        subprocess.run([*base_command, "pytest"], check=True)

    def _requirements_fingerprint(self) -> str:
        identity = json.dumps(
            {
                "content": self.project.requirements_content,
                "path": self.project.requirements_path,
                "requirements": self.project.get_requirement_strings(),
                "runner": "pytest",
                "system_python": str(self.system_python),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(identity.encode()).hexdigest()


def _project_root(project: Project) -> Path:
    location = Path(project.absolute_path or project.path).expanduser().resolve()
    return location.parent if location.is_file() else location
