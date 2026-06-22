import subprocess
from pathlib import Path

from pymut4se.execution import PythonExecutionEnvironment
from pymut4se.model import Project


def _fake_venv_creation(
    environment: PythonExecutionEnvironment,
    calls: list[list[str]],
):
    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
        calls.append(command)
        if command[1:3] == ["-m", "venv"]:
            environment.python_executable.parent.mkdir(parents=True, exist_ok=True)
            environment.python_executable.touch()
        return subprocess.CompletedProcess(command, 0)

    return fake_run


def test_prepares_and_reuses_a_project_virtual_environment(temp_path: Path, monkeypatch) -> None:
    project = Project("demo", ".", absolute_path=temp_path.as_posix())
    environment = PythonExecutionEnvironment.for_project(project)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "pymut4se.execution.environment.subprocess.run",
        _fake_venv_creation(environment, calls),
    )

    assert environment.prepare() is environment
    environment.prepare()

    assert environment.is_prepared
    assert environment.path == temp_path / ".pymut4se" / "venvs" / project.project_id
    assert len(calls) == 2
    assert calls[0] == [str(environment.system_python), "-m", "venv", str(environment.path)]
    assert calls[1][-1] == "pytest"
    assert environment.is_current
    assert len(environment.environment_id) == 64


def test_installs_an_existing_requirements_file_and_tracks_its_fingerprint(
    temp_path: Path,
    monkeypatch,
) -> None:
    requirements_path = temp_path / "requirements.txt"
    requirements_path.write_text("example-package==1\n", encoding="utf-8")
    project = Project(
        "demo",
        ".",
        absolute_path=temp_path.as_posix(),
        requirements_path=requirements_path.as_posix(),
        requirements_content=requirements_path.read_text(encoding="utf-8"),
        requirements=["example-package==1"],
    )
    environment = PythonExecutionEnvironment.for_project(project)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "pymut4se.execution.environment.subprocess.run",
        _fake_venv_creation(environment, calls),
    )

    environment.prepare()
    environment.prepare()

    assert len(calls) == 3
    assert calls[1][-2:] == ["-r", str(requirements_path)]
    assert calls[2][-1] == "pytest"
    assert (environment.path / ".pymut4se-requirements").is_file()


def test_uses_normalized_requirement_strings_when_the_manifest_is_unavailable(
    temp_path: Path,
    monkeypatch,
) -> None:
    project = Project(
        "demo",
        ".",
        absolute_path=temp_path.as_posix(),
        requirements_path=(temp_path / "missing.txt").as_posix(),
        requirements=["first>=1", "second"],
    )
    environment = PythonExecutionEnvironment.for_project(project)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "pymut4se.execution.environment.subprocess.run",
        _fake_venv_creation(environment, calls),
    )

    environment.prepare()

    assert calls[1][-2:] == ["first>=1", "second"]
    assert calls[2][-1] == "pytest"
