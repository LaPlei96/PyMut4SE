from __future__ import annotations

import re
from pathlib import Path


def extract_requirements(root: Path) -> tuple[str | None, str | None, list[str]]:
    """Find and parse the nearest requirements file for an explored path.

    The search walks upward and prefers ``requirements.txt`` over
    ``pyproject.toml`` within each directory. The result contains the source path,
    raw content and deduplicated requirement specifications.
    """
    search_root = root.parent if root.is_file() else root
    for directory in (search_root, *search_root.parents):
        for file_name in ("requirements.txt", "pyproject.toml"):
            candidate = directory / file_name
            if candidate.is_file():
                content = candidate.read_text(encoding="utf-8")
                requirements = _parse_requirements(candidate, content)
                return candidate.as_posix(), content, requirements
    return None, None, []


def _parse_requirements(path: Path, content: str) -> list[str]:
    if path.name == "requirements.txt":
        return _parse_requirements_txt(content)
    return _parse_pyproject_requirements(content)


def _parse_requirements_txt(content: str) -> list[str]:
    requirements = []
    for line in content.splitlines():
        requirement = line.split("#", maxsplit=1)[0].strip()
        if requirement and not requirement.startswith(("-", "--")):
            requirements.append(requirement)
    return requirements


def _parse_pyproject_requirements(content: str) -> list[str]:
    try:
        import tomllib
    except ModuleNotFoundError:
        groups = _parse_pyproject_requirements_fallback(content)
    else:
        data = tomllib.loads(content)
        groups = _extract_pyproject_requirement_groups(data)

    requirements = []
    seen = set()
    for group_requirements in groups.values():
        for requirement in group_requirements:
            if requirement not in seen:
                seen.add(requirement)
                requirements.append(requirement)
    return requirements


def _extract_pyproject_requirement_groups(data: dict) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    project = data.get("project", {})
    if isinstance(project, dict):
        dependencies = project.get("dependencies", [])
        if isinstance(dependencies, list):
            groups["default"] = [requirement for requirement in dependencies if isinstance(requirement, str)]

        optional_dependencies = project.get("optional-dependencies", {})
        if isinstance(optional_dependencies, dict):
            for group_name, dependencies in optional_dependencies.items():
                if isinstance(dependencies, list):
                    groups[str(group_name)] = [
                        requirement for requirement in dependencies if isinstance(requirement, str)
                    ]

    dependency_groups = data.get("dependency-groups", {})
    if isinstance(dependency_groups, dict):
        for group_name, dependencies in dependency_groups.items():
            if isinstance(dependencies, list):
                groups[str(group_name)] = [requirement for requirement in dependencies if isinstance(requirement, str)]

    return groups


def _parse_pyproject_requirements_fallback(content: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    section = ""
    current_key = ""
    current_values: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        section_match = re.fullmatch(r"\[([^\]]+)\]", stripped)
        if section_match:
            _store_pyproject_group(groups, section, current_key, current_values)
            section = section_match.group(1)
            current_key = ""
            current_values = []
            continue

        key_match = re.match(r"([A-Za-z0-9_.-]+)\s*=\s*\[", stripped)
        if key_match:
            _store_pyproject_group(groups, section, current_key, current_values)
            current_key = key_match.group(1)
            current_values = _extract_quoted_strings(stripped)
            if stripped.endswith("]"):
                _store_pyproject_group(groups, section, current_key, current_values)
                current_key = ""
                current_values = []
            continue

        if current_key:
            current_values.extend(_extract_quoted_strings(stripped))
            if stripped.endswith("]"):
                _store_pyproject_group(groups, section, current_key, current_values)
                current_key = ""
                current_values = []

    _store_pyproject_group(groups, section, current_key, current_values)
    return groups


def _store_pyproject_group(groups: dict[str, list[str]], section: str, key: str, values: list[str]) -> None:
    if not key or not values:
        return
    if section == "project" and key == "dependencies":
        groups["default"] = values
    elif section == "dependency-groups":
        groups[key] = values
    elif section == "project.optional-dependencies":
        groups[key] = values


def _extract_quoted_strings(value: str) -> list[str]:
    matches = re.findall(r'"([^"]+)"|\'([^\']+)\'', value)
    return [double_quoted or single_quoted for double_quoted, single_quoted in matches]
