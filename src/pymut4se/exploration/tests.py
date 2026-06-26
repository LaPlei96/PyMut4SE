from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pymut4se.exploration.utils import is_path_within, iter_python_files, relative_path
from pymut4se.model import CodeChunk, Module, TestCase, TestSuite, TestTarget


@dataclass(frozen=True)
class _TargetCandidate:
    name: str
    evidence: str
    confidence: float
    source_line: int | None


@dataclass(frozen=True)
class _TargetInference:
    module: Module | None
    chunk: CodeChunk | None
    evidence: str
    confidence: float
    source_line: int | None


def find_test_files(source_root: Path, python_files: Iterable[Path]) -> tuple[Path, list[Path]]:
    """Find tests, including sibling test folders when exploring a ``src`` directory."""
    test_root = source_root.parent if source_root.name.lower() == "src" else source_root
    test_files = {path for path in python_files if is_test_path(source_root, path)}

    if test_root != source_root:
        test_files.update(
            path for pattern in ("test_*.py", "*_test.py") for path in test_root.glob(pattern) if path.is_file()
        )
        for directory_name in ("test", "tests"):
            test_directory = test_root / directory_name
            if test_directory.is_dir():
                test_files.update(iter_python_files(test_directory))

    return test_root, sorted(test_files)


def discover_tests(
    source_root: Path,
    test_files: list[Path],
    modules: list[Module],
    chunks: list[CodeChunk],
) -> tuple[list[TestSuite], list[TestCase]]:
    """Discover test suites and cases and connect them to likely targets."""
    test_suites_by_path = _discover_test_suite_directories(source_root, test_files)
    test_suites: list[TestSuite] = list(test_suites_by_path.values())
    test_cases: list[TestCase] = []

    for test_path in test_files:
        source = test_path.read_text(encoding="utf-8")
        suite_name = _test_suite_name(source_root, test_path)
        test_tree = ast.parse(source, filename=relative_path(source_root, test_path))
        import_links = _collect_import_links(test_tree)
        target_module = _guess_target_module(suite_name, modules, import_links)
        parent_suite = _nearest_test_suite(test_path.parent, test_suites_by_path)
        suite = TestSuite(
            name=suite_name,
            path=relative_path(source_root, test_path),
            suite_type="module",
            absolute_path=test_path.as_posix(),
            parent_id=parent_suite.suite_id if parent_suite else None,
            source=source,
            target_module_id=target_module.module_id if target_module else None,
        )
        if parent_suite is not None:
            parent_suite.children.append(suite)
        test_suites.append(suite)

        lines = source.splitlines(keepends=True)
        for test_node, test_name in _discover_test_functions(suite_name, test_tree):
            if test_node.end_lineno is None:
                continue

            code = "".join(lines[test_node.lineno - 1 : test_node.end_lineno])
            test_case = TestCase(
                name=test_name,
                suite_id=suite.suite_id,
                start_line=test_node.lineno,
                end_line=test_node.end_lineno,
                code=code,
            )
            inferences = _infer_targets(test_name, test_node, import_links, target_module, chunks, modules)
            test_case.targets.extend(
                TestTarget(
                    test_id=test_case.test_id,
                    module=inference.module,
                    chunk=inference.chunk,
                    evidence=inference.evidence,
                    confidence=inference.confidence,
                    source_line=inference.source_line,
                )
                for inference in inferences
            )
            suite.test_cases.append(test_case)
            test_cases.append(test_case)

    return test_suites, test_cases


def is_test_path(source_root: Path, path: Path) -> bool:
    """Return whether a Python path follows common test naming conventions."""
    relative_path = path.relative_to(source_root)
    path_parts = {part.lower() for part in relative_path.parts}
    stem = path.stem
    return "test" in path_parts or "tests" in path_parts or stem.startswith("test_") or stem.endswith("_test")


def _discover_test_suite_directories(source_root: Path, test_files: list[Path]) -> dict[Path, TestSuite]:
    directory_paths = sorted(
        {
            parent
            for test_path in test_files
            for parent in test_path.parents
            if is_path_within(parent, source_root) and _is_test_suite_directory(source_root, parent, test_files)
        }
    )
    suite_by_path: dict[Path, TestSuite] = {}

    for directory_path in directory_paths:
        parent_suite = _nearest_test_suite(directory_path.parent, suite_by_path)
        suite = TestSuite(
            name=_test_suite_name(source_root, directory_path),
            path=relative_path(source_root, directory_path),
            suite_type="directory",
            absolute_path=directory_path.as_posix(),
            parent_id=parent_suite.suite_id if parent_suite else None,
        )
        if parent_suite is not None:
            parent_suite.children.append(suite)
        suite_by_path[directory_path] = suite

    return suite_by_path


def _is_test_suite_directory(source_root: Path, directory_path: Path, test_files: list[Path]) -> bool:
    if directory_path == source_root:
        return False
    relative_parts = {part.lower() for part in directory_path.relative_to(source_root).parts}
    return bool(relative_parts & {"test", "tests"}) or any(
        test_path.parent == directory_path for test_path in test_files
    )


def _nearest_test_suite(directory_path: Path, suite_by_path: dict[Path, TestSuite]) -> TestSuite | None:
    current = directory_path
    while True:
        suite = suite_by_path.get(current)
        if suite is not None:
            return suite
        if current.parent == current:
            return None
        current = current.parent


def _discover_test_functions(
    suite_name: str,
    tree: ast.AST,
) -> Iterable[tuple[ast.AsyncFunctionDef | ast.FunctionDef, str]]:
    for node, qualified_name in _iter_function_nodes(tree):
        if qualified_name.split(".")[-1].startswith("test_"):
            yield node, f"{suite_name}.{qualified_name}"


def _guess_target_module(
    test_suite_name: str,
    modules: list[Module],
    import_links: dict[str, str],
) -> Module | None:
    candidates = [
        candidate
        for imported_name in import_links.values()
        for candidate in _target_module_import_candidates(imported_name)
    ]
    candidates.extend(_target_module_name_candidates(test_suite_name))

    for candidate in candidates:
        matches = _matching_modules(candidate, modules)
        if len(matches) == 1:
            return matches[0]

    return None


def _target_module_import_candidates(imported_name: str) -> list[str]:
    candidates = [imported_name]
    if "." in imported_name:
        candidates.append(imported_name.rsplit(".", maxsplit=1)[0])
    return candidates


def _infer_targets(
    test_name: str,
    test_node: ast.AST,
    import_links: dict[str, str],
    target_module: Module | None,
    chunks: list[CodeChunk],
    modules: list[Module],
) -> list[_TargetInference]:
    candidates = _called_target_candidates(test_node, import_links)
    candidates.extend(
        _TargetCandidate(name, "name_match", 0.4, None) for name in _target_chunk_name_candidates(test_name)
    )
    modules_by_id = {module.module_id: module for module in modules}
    inferences: dict[tuple[str | None, str | None, str, int | None], _TargetInference] = {}

    for candidate in candidates:
        search_chunks = _candidate_target_chunks([candidate.name], target_module, chunks, modules)
        for chunk in search_chunks:
            if not _chunk_matches_candidate(chunk, candidate.name):
                continue
            module = modules_by_id.get(chunk.module_id)
            key = (module.module_id if module else None, chunk.chunk_id, candidate.evidence, candidate.source_line)
            inferences[key] = _TargetInference(
                module=module,
                chunk=chunk,
                evidence=candidate.evidence,
                confidence=candidate.confidence,
                source_line=candidate.source_line,
            )

    if not inferences and target_module is not None:
        evidence = "import" if import_links else "name_match"
        confidence = 0.65 if import_links else 0.4
        inference = _TargetInference(target_module, None, evidence, confidence, None)
        inferences[(target_module.module_id, None, evidence, None)] = inference

    return sorted(inferences.values(), key=lambda inference: inference.confidence, reverse=True)


def _collect_import_links(tree: ast.AST) -> dict[str, str]:
    links: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".")[0]
                links[local_name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                local_name = alias.asname or alias.name
                links[local_name] = f"{node.module}.{alias.name}"
                links.setdefault(alias.name, node.module)
    return links


def _called_target_candidates(test_node: ast.AST, import_links: dict[str, str]) -> list[_TargetCandidate]:
    candidates: list[_TargetCandidate] = []
    for node in ast.walk(test_node):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        if call_name is None:
            continue
        evidence = "qualified_call" if "." in call_name else "direct_call"
        candidates.append(_TargetCandidate(call_name, evidence, 0.8, node.lineno))
        root_name = call_name.split(".")[0]
        if root_name in import_links:
            suffix = call_name.removeprefix(root_name).lstrip(".")
            imported_name = import_links[root_name]
            expanded_name = f"{imported_name}.{suffix}" if suffix else imported_name
            confidence = 0.95 if suffix else 0.98
            candidates.append(_TargetCandidate(expanded_name, evidence, confidence, node.lineno))
    return _unique_candidates(candidates)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent_name = _call_name(node.value)
        return f"{parent_name}.{node.attr}" if parent_name else node.attr
    return None


def _candidate_target_chunks(
    candidate_names: list[str],
    target_module: Module | None,
    chunks: list[CodeChunk],
    modules: list[Module],
) -> list[CodeChunk]:
    if target_module is not None:
        return [chunk for chunk in chunks if chunk.module_id == target_module.module_id]

    module_ids = set()
    for candidate_name in candidate_names:
        module_name = ".".join(candidate_name.split(".")[:-1])
        if not module_name:
            continue
        module_ids.update(module.module_id for module in _matching_modules(module_name, modules))

    if module_ids:
        return [chunk for chunk in chunks if chunk.module_id in module_ids]
    return chunks


def _chunk_matches_candidate(chunk: CodeChunk, candidate_name: str) -> bool:
    leaf_name = candidate_name.split(".")[-1]
    return (
        chunk.function_name == candidate_name
        or chunk.function_name == leaf_name
        or chunk.function_name.endswith(f".{leaf_name}")
    )


def _matching_modules(candidate_name: str, modules: list[Module]) -> list[Module]:
    return [module for module in modules if module.name == candidate_name or module.name.endswith(f".{candidate_name}")]


def _unique_candidates(candidates: list[_TargetCandidate]) -> list[_TargetCandidate]:
    return list(dict.fromkeys(candidates))


def _test_suite_name(source_root: Path, path: Path) -> str:
    relative_path = path.relative_to(source_root)
    if path.is_file():
        relative_path = relative_path.with_suffix("")
    return ".".join(relative_path.parts)


def _target_module_name_candidates(test_module_name: str) -> list[str]:
    parts = [part for part in test_module_name.split(".") if part not in {"test", "tests"}]
    if not parts:
        return []

    last_part = parts[-1]
    if last_part.startswith("test_"):
        parts[-1] = last_part.removeprefix("test_")
    elif last_part.endswith("_test"):
        parts[-1] = last_part.removesuffix("_test")
    else:
        return []

    candidates = [".".join(parts)]
    if len(parts) > 1:
        candidates.append(parts[-1])
    return candidates


def _target_chunk_name_candidates(test_chunk_name: str) -> list[str]:
    leaf_name = test_chunk_name.split(".")[-1]
    if not leaf_name.startswith("test_"):
        return []

    candidate = leaf_name.removeprefix("test_")
    candidates = [candidate]
    while "_" in candidate:
        candidate = candidate.rsplit("_", maxsplit=1)[0]
        candidates.append(candidate)
    return candidates


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
