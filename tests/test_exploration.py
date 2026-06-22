from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.exploration import explore_path
from pymut4se.model import Base, Project


def test_explore_path_builds_a_persistable_relationship_graph(temp_path: Path) -> None:
    source_path = temp_path / "src"
    package_path = source_path / "demo"
    tests_path = temp_path / "tests"
    package_path.mkdir(parents=True)
    tests_path.mkdir()
    (package_path / "__init__.py").write_text("", encoding="utf-8")
    (package_path / "math.py").write_text(
        "def add(left, right):\n    return left + right\n",
        encoding="utf-8",
    )
    (tests_path / "test_math.py").write_text(
        "from demo.math import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )

    result = explore_path(source_path)

    assert result.project.packages == result.packages
    assert result.project.modules == result.modules
    assert result.project.code_chunks == result.code_chunks
    assert result.project.test_suites == result.test_suites
    assert result.project.test_cases == result.test_cases
    assert result.modules[0].package is result.packages[0]
    assert result.modules[0].code_chunks == result.code_chunks
    assert result.test_cases[0].target_chunks == result.code_chunks
    assert result.test_cases[0].targets[0].evidence == "direct_call"
    assert result.test_cases[0].targets[0].confidence == 0.98
    assert result.test_cases[0].targets[0].source_line == 4

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(result.project)
        session.commit()
        session.expire_all()

        stored_project = session.get(Project, result.project.project_id)
        assert stored_project is not None
        assert stored_project.module_count == 1
        assert stored_project.code_chunk_count == 1
        assert stored_project.test_case_count == 1
        assert stored_project.test_cases[0].targets[0].chunk is stored_project.code_chunks[0]


def test_project_root_exploration_prunes_environments_and_caches(temp_path: Path) -> None:
    (temp_path / "application.py").write_text("def run():\n    return True\n", encoding="utf-8")
    for excluded_directory in (".venv", "venv", ".pytest_cache", "__pycache__", ".git"):
        directory = temp_path / excluded_directory
        directory.mkdir()
        (directory / "ignored.py").write_text("def ignored():\n    return False\n", encoding="utf-8")

    result = explore_path(temp_path)

    assert [module.path for module in result.modules] == ["application.py"]
    assert [chunk.function_name for chunk in result.code_chunks] == ["run"]


def test_exploration_discovers_nested_packages_classes_and_functions(temp_path: Path) -> None:
    nested_package = temp_path / "parent" / "child"
    nested_package.mkdir(parents=True)
    (temp_path / "parent" / "__init__.py").write_text("", encoding="utf-8")
    (nested_package / "__init__.py").write_text("", encoding="utf-8")
    (nested_package / "service.py").write_text(
        """
class Service:
    def execute(self):
        def normalize(value):
            return value
        return normalize(True)
""".lstrip(),
        encoding="utf-8",
    )

    result = explore_path(temp_path)

    assert [package.name for package in result.packages] == ["parent", "parent.child"]
    assert result.packages[1].parent is result.packages[0]
    assert [module.name for module in result.modules] == ["parent.child.service"]
    assert [chunk.function_name for chunk in result.code_chunks] == [
        "Service.execute",
        "Service.execute.normalize",
    ]


def test_exploration_accepts_a_single_python_file(temp_path: Path) -> None:
    source = temp_path / "standalone.py"
    source.write_text("async def execute():\n    return None\n", encoding="utf-8")

    result = explore_path(source)

    assert result.project.name == "standalone"
    assert [module.name for module in result.modules] == ["standalone"]
    assert [chunk.function_name for chunk in result.code_chunks] == ["execute"]


def test_exploration_reports_invalid_input_paths(temp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="path does not exist"):
        explore_path(temp_path / "missing")

    text_file = temp_path / "example.txt"
    text_file.write_text("not Python", encoding="utf-8")
    with pytest.raises(ValueError, match="path is not a Python file"):
        explore_path(text_file)


def test_target_inference_distinguishes_qualified_calls_and_module_only_links(temp_path: Path) -> None:
    package_path = temp_path / "src" / "demo"
    tests_path = temp_path / "tests"
    package_path.mkdir(parents=True)
    tests_path.mkdir()
    (package_path / "__init__.py").write_text("", encoding="utf-8")
    (package_path / "math.py").write_text(
        "def add(left, right):\n    return left + right\n",
        encoding="utf-8",
    )
    (tests_path / "test_math.py").write_text(
        """
import demo.math as math

def test_add():
    assert math.add(1, 2) == 3

def test_module_available():
    assert math
""".lstrip(),
        encoding="utf-8",
    )

    result = explore_path(temp_path / "src")
    cases = {case.name.split(".")[-1]: case for case in result.test_cases}

    qualified_target = cases["test_add"].targets[0]
    assert qualified_target.evidence == "qualified_call"
    assert qualified_target.confidence == 0.95
    assert qualified_target.chunk is result.code_chunks[0]

    module_target = cases["test_module_available"].targets[0]
    assert module_target.evidence == "import"
    assert module_target.confidence == 0.65
    assert module_target.module is result.modules[0]
    assert module_target.chunk is None
