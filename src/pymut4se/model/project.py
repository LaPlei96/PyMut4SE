from enum import Enum
from dataclasses import dataclass, field
import uuid
from typing import Optional
from pathlib import Path


class ProjectType(Enum):
    STANDALONE = "standalone"
    PROJECT = "project"


@dataclass
class Project:
    pl: str 
    working_dir: Path 
    type: ProjectType = ProjectType.STANDALONE
    requirements_path: Optional[Path] = None
    project_uuid: uuid.UUID = field(default_factory=lambda: uuid.uuid4())
