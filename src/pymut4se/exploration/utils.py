from pathlib import Path


EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".pymut4se",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "env",
        "node_modules",
        "venv",
    }
)


def iter_python_files(path: Path) -> list[Path]:
    """Return Python files while pruning environments, caches, and build output."""
    if path.is_file():
        if path.suffix != ".py":
            msg = f"path is not a Python file: {path}"
            raise ValueError(msg)
        return [path]

    python_files = []
    for directory, directory_names, file_names in path.walk():
        directory_names[:] = [name for name in directory_names if name.lower() not in EXCLUDED_DIRECTORY_NAMES]
        python_files.extend(directory / name for name in file_names if name.endswith(".py"))
    return sorted(python_files)


def is_path_within(path: Path, root: Path) -> bool:
    """Return whether a path is equal to or contained by a root path."""
    return path == root or root in path.parents


def relative_path(root: Path, path: Path) -> str:
    """Return a POSIX-style path relative to a root path."""
    return path.relative_to(root).as_posix()
