from pathlib import Path

import pytest

from pymut4se.exploration.utils import is_path_within, iter_python_files, relative_path


def test_iter_python_files_accepts_a_single_python_file(temp_path: Path) -> None:
    source = temp_path / "example.py"
    source.write_text("value = 1\n", encoding="utf-8")

    assert iter_python_files(source) == [source]


def test_iter_python_files_rejects_a_non_python_file(temp_path: Path) -> None:
    source = temp_path / "README.md"
    source.write_text("documentation", encoding="utf-8")

    with pytest.raises(ValueError, match="path is not a Python file"):
        iter_python_files(source)


def test_path_helpers_use_posix_relative_paths(temp_path: Path) -> None:
    nested = temp_path / "package" / "module.py"

    assert is_path_within(nested, temp_path)
    assert not is_path_within(temp_path, nested)
    assert relative_path(temp_path, nested) == "package/module.py"
