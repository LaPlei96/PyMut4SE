from enum import Enum
from dataclasses import dataclass, field
import uuid
from typing import Any, Optional


class ExecutionEnvironmentType(Enum):
    LOCAL = "local"
    CONTAINER = "container"


@dataclass
class ExecutionEnvironment:
    name: str
    type: ExecutionEnvironmentType
    version: str
    os: str
    version_details: Any
    python_executable: Optional[str] = None
    container_image: Optional[str] = None
    environment_id: uuid.UUID = field(default_factory=lambda: uuid.uuid4())
    
