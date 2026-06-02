import hashlib
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class CodeChunk:
    """A CodeChunk represents a piece of code that can be executed, along with metadata about its origin and mutation details."""
    code: str
    pl: str
    function_name: str
    mutation_degree: int = 0

    location: Optional[Path] = None  

    original_code: Optional[str] = None
    parent_id: Optional[str] = None
    line_changed: Optional[int] = None

    mutation_type: Optional[str] = None
    mutation_operator: Optional[str] = None
    mutation_tool: Optional[str] = None
    chunk_id: str = field(default="")

    def __post_init__(self):
        if not self.chunk_id:
            self.chunk_id = hashlib.sha256((self.code + (str(self.location) if self.location else "")).encode()).hexdigest()
