import hashlib
from collections.abc import Callable

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pymut4se.model import Base, CodeChunk, Module, Package, Project, Requirement
from pymut4se.model import TestCase as ModelTestCase
from pymut4se.model import TestSuite as ModelTestSuite
from pymut4se.model import TestTarget as ModelTestTarget


def test_ids_keep_the_original_identity_scheme() -> None:
    package = Package("pkg", "src/pkg")
    module = Module("example", "src/pkg/example.py", package.package_id)
    chunk = CodeChunk("def f(): pass", module.module_id, "f", "function", 1, 1)
    suite = ModelTestSuite("tests", "tests", "directory")
    case = ModelTestCase("test_f", suite.suite_id, start_line=4)
    project = Project("demo", ".", "/work/demo")
    requirement = Requirement(project.project_id, "pytest>=9")

    expected_identities = {
        package.package_id: ":pkg:src/pkg",
        module.module_id: f"{package.package_id}:example:src/pkg/example.py",
        chunk.chunk_id: f"{module.module_id}:f:function:1:1:def f(): pass",
        suite.suite_id: ":tests:tests:directory",
        case.test_id: f"{suite.suite_id}:test_f:4",
        project.project_id: "demo:.:/work/demo",
        requirement.requirement_id: f"{project.project_id}:pytest>=9",
    }
    for generated_id, identity in expected_identities.items():
        assert generated_id == hashlib.sha256(identity.encode()).hexdigest()


def test_models_round_trip_with_relationships() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    package = Package("pkg", "src/pkg")
    module = Module("example", "src/pkg/example.py", package.package_id)
    chunk = CodeChunk("def f(): pass", module.module_id, "f", "function", 1, 1)
    suite = ModelTestSuite("tests", "tests", "directory")
    case = ModelTestCase("test_f", suite.suite_id)
    case.targets.append(
        ModelTestTarget(
            test_id=case.test_id,
            module=module,
            chunk=chunk,
            evidence="direct_call",
            confidence=0.98,
            source_line=4,
        )
    )
    project = Project(
        "demo",
        ".",
        requirements_path="requirements.txt",
        requirements_content="requests>=2\npytest\n",
        requirements=["requests>=2", "pytest"],
    )
    project.packages.append(package)
    project.modules.append(module)
    project.code_chunks.append(chunk)
    project.test_suites.append(suite)
    project.test_cases.append(case)

    with Session(engine) as session:
        session.add(project)
        session.commit()
        session.expire_all()

        stored_project = session.get(Project, project.project_id)
        assert stored_project is not None
        assert stored_project.requirements_path == "requirements.txt"
        assert stored_project.requirements_content == "requests>=2\npytest\n"
        assert stored_project.get_requirement_strings() == ["requests>=2", "pytest"]
        assert all(requirement.project is stored_project for requirement in stored_project.requirements)
        another_module = Module("another", "src/pkg/another.py", package.package_id)
        stored_project.modules.append(another_module)
        session.commit()
        session.expire_all()

        stored_chunk = session.get(CodeChunk, chunk.chunk_id)
        stored_project = session.get(Project, project.project_id)
        assert stored_chunk is not None
        assert stored_chunk.function_name == "f"
        assert stored_project is not None
        assert {item.module_id for item in stored_project.modules} == {
            module.module_id,
            another_module.module_id,
        }
        stored_case = session.get(ModelTestCase, case.test_id)
        assert stored_case is not None
        assert stored_case.target_chunks == [stored_chunk]


def test_project_collections_have_independent_defaults_and_counts() -> None:
    first = Project("first", "first")
    second = Project("second", "second")
    package = Package("pkg", "pkg")

    first.packages.append(package)

    assert first.package_count == 1
    assert second.package_count == 0
    assert package.project is first
    assert first.requirements is not second.requirements


def test_project_builds_normalized_requirements_and_string_fallback() -> None:
    project = Project(
        "demo",
        ".",
        requirements=["requests>=2", "pytest", "requests>=2"],
    )

    assert project.requirement_count == 2
    assert project.get_requirement_strings() == ["requests>=2", "pytest"]
    assert [requirement.position for requirement in project.requirements] == [0, 1]
    assert all(requirement.project is project for requirement in project.requirements)
    assert project.get_requirement_strings() is not project.get_requirement_strings()


def test_package_hierarchy_and_module_relationships_are_bidirectional() -> None:
    parent = Package("parent", "parent")
    child = Package("parent.child", "parent/child", parent_id=parent.package_id)
    module = Module("parent.child.example", "parent/child/example.py", child.package_id)

    parent.children.append(child)
    child.modules.append(module)

    assert child.parent is parent
    assert module.package is child
    assert child in parent.children
    assert module in child.modules


def test_module_original_chunks_relationship_filters_mutants() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    module = Module("example", "example.py")
    original = CodeChunk("def f(): pass", module.module_id, "f", "function", 1, 1)
    mutant = CodeChunk(
        "def f(): return None",
        module.module_id,
        "f",
        "function",
        1,
        1,
        mutation_degree=1,
        original_id=original.chunk_id,
        parent_id=original.chunk_id,
    )
    mutant.original = original
    mutant.parent = original
    module.code_chunks.extend([original, mutant])

    with Session(engine) as session:
        session.add(module)
        session.commit()
        session.expire_all()

        stored_module = session.get(Module, module.module_id)
        assert stored_module is not None
        assert stored_module.original_code_chunks == [original]
        assert mutant.parent is original
        assert original.children == [mutant]
        assert mutant.original is original
        assert original.derived_chunks == [mutant]


def test_code_chunk_uses_function_name_and_accepts_explicit_id() -> None:
    generated = CodeChunk("def f(): pass", "module", "f", "function", 1, 1)
    explicit = CodeChunk("value = 1", "module", "assignment", "statement", 2, 2, chunk_id="custom")

    assert generated.function_name == "f"
    assert explicit.function_name == "assignment"
    assert explicit.chunk_id == "custom"


def test_test_suite_hierarchy_and_case_targets_are_bidirectional() -> None:
    module = Module("example", "example.py")
    chunk = CodeChunk("def f(): pass", module.module_id, "f", "function", 1, 1)
    directory = ModelTestSuite("tests", "tests", "directory")
    suite = ModelTestSuite("tests.test_example", "tests/test_example.py", "module", parent_id=directory.suite_id)
    case = ModelTestCase("tests.test_example.test_f", suite.suite_id)
    target = ModelTestTarget(
        test_id=case.test_id,
        module=module,
        chunk=chunk,
        evidence="qualified_call",
        confidence=0.95,
        source_line=8,
    )
    case.targets.append(target)

    directory.children.append(suite)
    suite.test_cases.append(case)

    assert suite.parent is directory
    assert case.suite is suite
    assert case.target_chunk is chunk
    assert case.target_module is module
    assert case.target_chunks == [chunk]
    assert case.target_modules == [module]
    assert target.test_case is case
    assert module.test_targets == [target]
    assert chunk.test_targets == [target]


def test_test_case_orders_unique_targets_by_confidence() -> None:
    first_module = Module("first", "first.py")
    second_module = Module("second", "second.py")
    first_chunk = CodeChunk("def first(): pass", first_module.module_id, "first", "function", 1, 1)
    second_chunk = CodeChunk("def second(): pass", second_module.module_id, "second", "function", 1, 1)
    suite = ModelTestSuite("tests", "tests", "directory")
    case = ModelTestCase("test_both", suite.suite_id)
    case.targets.extend(
        [
            ModelTestTarget(case.test_id, "name_match", 0.4, module=first_module, chunk=first_chunk),
            ModelTestTarget(case.test_id, "direct_call", 0.98, module=second_module, chunk=second_chunk),
            ModelTestTarget(case.test_id, "direct_call", 0.8, module=first_module, chunk=first_chunk),
        ]
    )

    assert case.target_chunk is second_chunk
    assert case.target_chunks == [second_chunk, first_chunk]
    assert case.target_modules == [second_module, first_module]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: Package("", "src/pkg"), "name must not be empty"),
        (lambda: Requirement("project", ""), "specification must not be empty"),
        (lambda: Requirement("project", "pytest", position=-1), "position must be greater than or equal to 0"),
        (
            lambda: CodeChunk("pass", "module", "chunk", "statement", 0, 1),
            "start_line must be greater than or equal to 1",
        ),
        (
            lambda: CodeChunk("pass", "module", "chunk", "statement", 2, 1),
            "end_line must be greater than or equal to start_line",
        ),
        (
            lambda: CodeChunk("pass", "module", "chunk", "statement", 1, 1, mutation_degree=-1),
            "mutation_degree must be greater than or equal to 0",
        ),
        (
            lambda: CodeChunk("pass", "module", "", "statement", 1, 1),
            "function_name must not be empty",
        ),
        (
            lambda: CodeChunk("pass", "module", "chunk", "statement", 1, 1, original_id="original"),
            "a degree-zero code chunk must not reference an original",
        ),
        (
            lambda: CodeChunk("pass", "module", "chunk", "statement", 1, 1, mutation_degree=1),
            "a mutated code chunk must reference its degree-zero original",
        ),
        (
            lambda: ModelTestSuite("tests", "tests", "invalid"),
            "suite_type must be either 'directory' or 'module'",
        ),
        (lambda: ModelTestCase("test_f", ""), "suite_id must not be empty"),
        (
            lambda: ModelTestTarget("test", "unknown", 0.5, module_id="module"),
            "unsupported target evidence",
        ),
        (
            lambda: ModelTestTarget("test", "manual", 1.5, module_id="module"),
            "confidence must be between 0 and 1",
        ),
        (
            lambda: ModelTestTarget("test", "manual", 1.0),
            "a test target must reference a module or code chunk",
        ),
    ],
)
def test_domain_validation_is_preserved(factory: Callable[[], object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        factory()
