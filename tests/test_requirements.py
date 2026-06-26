from pathlib import Path

from pymut4se.exploration import explore_path
from pymut4se.exploration.requirements import extract_requirements


def test_extract_requirements_txt_ignores_comments_and_options(temp_path: Path) -> None:
    requirements_path = temp_path / "requirements.txt"
    requirements_path.write_text(
        "requests>=2\npytest # test runner\n-r common.txt\n--index-url https://example.invalid\n",
        encoding="utf-8",
    )

    path, content, requirements = extract_requirements(temp_path)

    assert path == requirements_path.as_posix()
    assert content == requirements_path.read_text(encoding="utf-8")
    assert requirements == ["requests>=2", "pytest"]


def test_extract_pyproject_requirements_are_flattened_and_deduplicated(temp_path: Path) -> None:
    pyproject_path = temp_path / "pyproject.toml"
    pyproject_path.write_text(
        """
[project]
dependencies = ["sqlalchemy>=2"]

[project.optional-dependencies]
docs = ["pdoc"]

[dependency-groups]
test = ["pytest", "sqlalchemy>=2"]
""".strip(),
        encoding="utf-8",
    )

    path, _, requirements = extract_requirements(temp_path / "src")

    assert path == pyproject_path.as_posix()
    assert requirements == ["sqlalchemy>=2", "pdoc", "pytest"]


def test_exploration_connects_normalized_requirements_to_the_project(temp_path: Path) -> None:
    source_path = temp_path / "src"
    source_path.mkdir()
    (source_path / "application.py").write_text("def run():\n    return True\n", encoding="utf-8")
    pyproject_path = temp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[project]\ndependencies = ["sqlalchemy>=2", "pytest"]\n',
        encoding="utf-8",
    )

    result = explore_path(source_path)

    assert result.project.requirements_path == pyproject_path.as_posix()
    assert result.project.requirements_content == pyproject_path.read_text(encoding="utf-8")
    assert result.project.get_requirement_strings() == ["sqlalchemy>=2", "pytest"]
    assert all(requirement.project is result.project for requirement in result.project.requirements)
