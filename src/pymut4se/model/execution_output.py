from dataclasses import dataclass, field
import uuid
from typing import Any


@dataclass
class ExecutionOutput:
    success: bool
    output: Any
    code_chunk_id: str
    execution_environment_id: uuid.UUID
    input_id: uuid.UUID
    error_message: str = ""
    time_taken: float = 0.0
    execution_id: uuid.UUID = field(default_factory=lambda: uuid.uuid4())
