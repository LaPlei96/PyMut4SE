from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pymut4se.exploration.requirements import extract_requirements
from pymut4se.exploration.tests import discover_tests, find_test_files
from pymut4se.exploration.utils import is_path_within, iter_python_files, relative_path
from pymut4se.model import CodeChunk, Module, Package, Project, TestCase, TestSuite


@dataclass
class ExplorationResult:
    """Connected objects discovered during one filesystem traversal.

    The entity lists contain the same instances exposed through the root project's
    relationships. Persist the entire graph with ``session.add(result.project)``.
    """

    project: Project
    packages: list[Package]
    modules: list[Module]
    code_chunks: list[CodeChunk]
    test_suites: list[TestSuite]
    test_cases: list[TestCase]


def explore_path(path: str | Path) -> ExplorationResult:
    """Explore a Python file or directory and build a connected ORM graph.

    Args:
        path: Python file, source directory, or project root to inspect.

    Returns:
        The project aggregate and its discovered entity collections.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If ``path`` is a non-Python file.
        SyntaxError: If a discovered Python file cannot be parsed.

    When ``path`` is a directory named ``src``, sibling ``test`` and ``tests``
    directories are inspected as well. Environments, caches, VCS metadata, and
    build output are pruned during directory traversal.
    """
    root = Path(path).expanduser().resolve()
    if not root.exists():
        msg = f"path does not exist: {root}"
        raise FileNotFoundError(msg)

    source_root = root.parent if root.is_file() else root
    python_files = iter_python_files(root)
    test_root, test_files = find_test_files(source_root, python_files)
    test_file_set = set(test_files)
    production_files = [
        file_path for file_path in python_files if file_path not in test_file_set and file_path.name != "__init__.py"
    ]

    package_by_path = _discover_packages(source_root, production_files)
    modules = _discover_modules(source_root, production_files, package_by_path)
    module_by_path = {Path(module.path): module for module in modules}

    chunks = []
    for module_path in sorted(module_by_path):
        module = module_by_path[module_path]
        discovered_chunks = _discover_function_chunks(module)
        module.code_chunks.extend(discovered_chunks)
        chunks.extend(discovered_chunks)

    test_suites, test_cases = discover_tests(test_root, test_files, modules, chunks)
    packages = sorted(package_by_path.values(), key=lambda package: package.path)
    project = _build_project(root, source_root, packages, modules, chunks, test_suites, test_cases)

    return ExplorationResult(
        project=project,
        packages=packages,
        modules=modules,
        code_chunks=chunks,
        test_suites=test_suites,
        test_cases=test_cases,
    )


def _build_project(
    root: Path,
    source_root: Path,
    packages: list[Package],
    modules: list[Module],
    chunks: list[CodeChunk],
    test_suites: list[TestSuite],
    test_cases: list[TestCase],
) -> Project:
    requirements_path, requirements_content, requirements = extract_requirements(root)
    return Project(
        name=root.stem if root.is_file() else root.name,
        path=relative_path(source_root.parent, root) if root != source_root.parent else root.name,
        absolute_path=root.as_posix(),
        requirements_path=requirements_path,
        requirements_content=requirements_content,
        requirements=requirements,
        packages=packages,
        modules=modules,
        code_chunks=chunks,
        test_suites=test_suites,
        test_cases=test_cases,
    )


def _discover_packages(source_root: Path, python_files: Iterable[Path]) -> dict[Path, Package]:
    package_paths = sorted(
        {
            parent
            for file_path in python_files
            for parent in file_path.parents
            if is_path_within(parent, source_root) and (parent / "__init__.py").is_file()
        }
    )
    package_by_path: dict[Path, Package] = {}

    for package_path in package_paths:
        parent_package = _nearest_parent_package(package_path, package_by_path)
        package = Package(
            name=_package_name(source_root, package_path, parent_package),
            path=relative_path(source_root, package_path),
            absolute_path=package_path.as_posix(),
            parent_id=parent_package.package_id if parent_package else None,
        )
        if parent_package is not None:
            parent_package.children.append(package)
        package_by_path[package_path] = package

    return package_by_path


def _discover_modules(
    source_root: Path,
    python_files: list[Path],
    package_by_path: dict[Path, Package],
) -> list[Module]:
    modules = []
    for module_path in sorted(python_files):
        package = _nearest_package(module_path.parent, package_by_path)
        module = Module(
            name=_module_name(source_root, module_path, package),
            path=relative_path(source_root, module_path),
            package_id=package.package_id if package else None,
            source=module_path.read_text(encoding="utf-8"),
        )
        if package is not None:
            package.modules.append(module)
        modules.append(module)
    return modules


def _discover_function_chunks(module: Module) -> list[CodeChunk]:
    tree = ast.parse(module.source or "", filename=module.path)
    lines = (module.source or "").splitlines(keepends=True)
    chunks: list[CodeChunk] = []

    for node, qualified_name in _iter_function_nodes(tree):
        if node.end_lineno is None:
            continue
        start_line = min((decorator.lineno for decorator in node.decorator_list), default=node.lineno)
        code = "".join(lines[start_line - 1 : node.end_lineno])
        chunks.append(
            CodeChunk(
                code=code,
                module_id=module.module_id,
                function_name=qualified_name,
                chunk_type="function",
                start_line=start_line,
                end_line=node.end_lineno,
            )
        )

    return chunks


def _iter_function_nodes(tree: ast.AST) -> Iterable[tuple[ast.AsyncFunctionDef | ast.FunctionDef, str]]:
    yield from _iter_function_nodes_in_body(getattr(tree, "body", []), ())


def _iter_function_nodes_in_body(
    body: list[ast.stmt],
    parents: tuple[str, ...],
) -> Iterable[tuple[ast.AsyncFunctionDef | ast.FunctionDef, str]]:
    for node in body:
        if isinstance(node, ast.ClassDef):
            yield from _iter_function_nodes_in_body(node.body, (*parents, node.name))
        elif isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            qualified_name = ".".join((*parents, node.name))
            yield node, qualified_name
            yield from _iter_function_nodes_in_body(node.body, (*parents, node.name))


def _nearest_parent_package(package_path: Path, package_by_path: dict[Path, Package]) -> Package | None:
    for parent in package_path.parents:
        if parent in package_by_path:
            return package_by_path[parent]
    return None


def _nearest_package(directory: Path, package_by_path: dict[Path, Package]) -> Package | None:
    current = directory
    while True:
        package = package_by_path.get(current)
        if package is not None:
            return package
        if current.parent == current:
            return None
        current = current.parent


def _package_name(source_root: Path, package_path: Path, parent_package: Package | None) -> str:
    if parent_package is not None:
        return f"{parent_package.name}.{package_path.name}"

    relative = package_path.relative_to(source_root)
    if relative.parts:
        return ".".join(relative.parts)
    return package_path.name


def _module_name(source_root: Path, module_path: Path, package: Package | None) -> str:
    if package is not None:
        if module_path.name == "__init__.py":
            return package.name

        relative = module_path.relative_to(source_root / Path(package.path)).with_suffix("")
        return ".".join((package.name, *relative.parts))

    relative = module_path.relative_to(source_root).with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)
