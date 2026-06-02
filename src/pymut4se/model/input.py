import pickle
import base64
from dataclasses import dataclass, field
import uuid
from typing import Any, Optional
from pathlib import Path


@dataclass
class Input:
    type: str  # "text" or "serialized"
    value: Any     # payload for execution
    function_name: str = ""
    mode: str = "standalone" 
    code_location: Optional[Path] = None
    working_dir: Optional[Path] = None
    test_command: Optional[str] = None
    timeout_seconds: Optional[int] = 2
    extra_env: Optional[dict] = None
    requirements_path: Optional[Path] = None
    input_id: uuid.UUID = field(default_factory=lambda: uuid.uuid4())


@dataclass
class ProgramInput:
    type: str
    value: str
    text_representation: str

    @staticmethod
    def from_value(value: tuple, text_representation: str) -> "ProgramInput":
        encoded_value = base64.b64encode(pickle.dumps(value)).decode("utf-8")
        return ProgramInput(type="serialized", value=encoded_value, text_representation=text_representation)
    
    @staticmethod
    def from_text_representation(text_representation: str) -> "ProgramInput":
        return ProgramInput(type="text", value=text_representation, text_representation=text_representation)
