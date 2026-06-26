from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Optional

from pymut4se.exploration import ExplorationResult
from pymut4se.model import CodeChunk


@dataclass(frozen=True)
class ProjectStatistics:
    """Compact overview of an explored project."""

    packages: int
    modules: int
    original_chunks: int
    test_suites: int
    test_cases: int
    test_links: int
    chunks_with_tests: int
    requirements: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"ProjectStatistics(packages={self.packages}, modules={self.modules}, "
            f"chunks={self.original_chunks}, tests={self.test_cases}, "
            f"tested_chunks={self.chunks_with_tests}, requirements={self.requirements})"
        )

    __repr__ = __str__


@dataclass(frozen=True)
class MutantStatistics:
    """Overview of generated mutants and their recorded executions."""

    total: int
    source_chunks: int
    by_degree: dict[int, int]
    by_type: dict[str, int]
    by_operator: dict[str, int]
    input_executions: int
    test_executions: int
    failed_tests: int

    def as_dict(self) -> dict[str, int | dict[int, int] | dict[str, int]]:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"MutantStatistics(total={self.total}, source_chunks={self.source_chunks}, "
            f"by_degree={self.by_degree}, by_type={self.by_type}, "
            f"input_executions={self.input_executions}, test_executions={self.test_executions}, "
            f"failed_tests={self.failed_tests})"
        )

    __repr__ = __str__


@dataclass(frozen=True)
class MutationScore:
    """Mutation-testing score with explicit inconclusive-result categories."""

    total: int
    killed: int
    survived: int
    untested: int
    incomplete: int
    errors: int
    score: Optional[float]

    @property
    def assessed(self) -> int:
        return self.killed + self.survived

    @property
    def percentage(self) -> Optional[float]:
        return self.score * 100 if self.score is not None else None

    def as_dict(self) -> dict[str, int | float | None]:
        return {
            "total": self.total,
            "assessed": self.assessed,
            "killed": self.killed,
            "survived": self.survived,
            "untested": self.untested,
            "incomplete": self.incomplete,
            "errors": self.errors,
            "score": self.score,
            "percentage": self.percentage,
        }

    def __str__(self) -> str:
        score = f"{self.percentage:.2f}%" if self.percentage is not None else "N/A"
        return (
            f"MutationScore(score={score}, killed={self.killed}, survived={self.survived}, "
            f"untested={self.untested}, incomplete={self.incomplete}, errors={self.errors})"
        )

    __repr__ = __str__


def project_statistics(result: ExplorationResult) -> ProjectStatistics:
    chunks_with_tests = sum(bool(chunk.related_test_cases) for chunk in result.code_chunks)
    return ProjectStatistics(
        packages=len(result.packages),
        modules=len(result.modules),
        original_chunks=len(result.code_chunks),
        test_suites=len(result.test_suites),
        test_cases=len(result.test_cases),
        test_links=sum(len(test_case.targets) for test_case in result.test_cases),
        chunks_with_tests=chunks_with_tests,
        requirements=len(result.project.requirements),
    )


def mutant_statistics(mutants: list[CodeChunk]) -> MutantStatistics:
    return MutantStatistics(
        total=len(mutants),
        source_chunks=len({mutant.original_id for mutant in mutants}),
        by_degree=dict(sorted(Counter(mutant.mutation_degree for mutant in mutants).items())),
        by_type=dict(sorted(Counter(mutant.mutation_type or "unknown" for mutant in mutants).items())),
        by_operator=dict(sorted(Counter(mutant.mutation_operator or "unknown" for mutant in mutants).items())),
        input_executions=sum(len(mutant.execution_outputs) for mutant in mutants),
        test_executions=sum(len(mutant.test_execution_outputs) for mutant in mutants),
        failed_tests=sum(not execution.success for mutant in mutants for execution in mutant.test_execution_outputs),
    )


def mutation_score(mutants: list[CodeChunk], *, environment_id: Optional[str] = None) -> MutationScore:
    """Classify mutants and score only conclusively killed or surviving ones."""
    unique_mutants = list({mutant.chunk_id: mutant for mutant in mutants}.values())
    counts = Counter(_mutant_outcome(mutant, environment_id=environment_id) for mutant in unique_mutants)
    killed = counts["killed"]
    survived = counts["survived"]
    assessed = killed + survived
    return MutationScore(
        total=len(unique_mutants),
        killed=killed,
        survived=survived,
        untested=counts["untested"],
        incomplete=counts["incomplete"],
        errors=counts["errors"],
        score=killed / assessed if assessed else None,
    )


def _mutant_outcome(mutant: CodeChunk, *, environment_id: Optional[str]) -> str:
    expected_tests = list(mutant.related_test_cases)
    if not expected_tests:
        project = mutant.project or (mutant.module.project if mutant.module is not None else None)
        if project is not None:
            expected_tests = list(project.test_cases)
    expected_test_ids = {test_case.test_id for test_case in expected_tests}
    if not expected_test_ids:
        return "untested"
    outputs = [
        output
        for output in mutant.test_execution_outputs
        if environment_id is None or output.environment_id == environment_id
    ]
    if not outputs:
        return "untested"
    if any(not output.success and output.return_code == 1 for output in outputs):
        return "killed"
    if any(not output.success for output in outputs):
        return "errors"
    executed_test_ids = {output.test_id for output in outputs}
    if expected_test_ids.issubset(executed_test_ids):
        return "survived"
    return "incomplete"
