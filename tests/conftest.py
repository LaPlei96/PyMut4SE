from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture
def temp_path() -> Iterator[Path]:
    """Provide a temporary path managed by Python's standard library."""
    with TemporaryDirectory(prefix="pymut4se-tests-") as directory:
        yield Path(directory)
