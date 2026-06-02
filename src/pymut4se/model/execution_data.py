from dataclasses import dataclass, field
import uuid
from typing import Optional
from pathlib import Path


@dataclass
class ExecutionData:
    """ExecutionData encapsulates all the necessary information for executing a code chunk, including the code itself, execution environment details, and metadata about the execution context."""
    pl: str
    function_name: str
    code_location: Optional[Path] = None  
    inputs_location: Optional[Path] = None
    actual_input: Optional[any] = None
    output: Optional[any] = None
    success: Optional[bool] = None
    error: Optional[bool] = None
    code_id: Optional[uuid.UUID] = None
    mode: str = "standalone" 
    python_executable: Optional[str] = None  
    test_command: Optional[str] = None  
    working_dir: Optional[Path] = None
    timeout_seconds: Optional[int] = 2
    extra_env: Optional[dict] = None
    container_image: Optional[str] = None  

    exec_id: uuid.UUID = field(default_factory=lambda: uuid.uuid4())



