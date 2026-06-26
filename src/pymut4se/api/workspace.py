from __future__ import annotations

from collections.abc import Sequence
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional, TypeAlias

from sqlalchemy.orm import Session

from pymut4se.api.operators import OperatorInfo, OperatorSelection, available_operators, resolve_operators
from pymut4se.api.statistics import (
    MutantStatistics,
    MutationScore,
    ProjectStatistics,
    mutant_statistics,
    mutation_score,
    project_statistics,
)
from pymut4se.execution import ParallelExecution, PythonExecutionEnvironment, StandalonePythonExecution
from pymut4se.exploration import ExplorationResult, explore_path
from pymut4se.model import (
    CodeChunk,
    ExecutionOutput,
    FunctionInput,
    Module,
    Package,
    Project,
    TestCase,
    TestExecutionOutput,
)
from pymut4se.mutation import generate_mutants

Selectable: TypeAlias = Package | Module | CodeChunk


class MutationWorkspace:
    """High-level workflow for exploring, mutating, and executing one project."""

    def __init__(self, exploration: ExplorationResult) -> None:
        self.exploration = exploration
        self.mutants: list[CodeChunk] = []
        self.inputs: list[FunctionInput] = []
        self.input_outputs: list[ExecutionOutput] = []
        self.test_outputs: list[TestExecutionOutput] = []
        self.environment: Optional[PythonExecutionEnvironment] = None

    def __str__(self) -> str:
        return (
            f"MutationWorkspace(project={self.project.name!r}, modules={len(self.modules)}, "
            f"chunks={len(self.chunks)}, mutants={len(self.mutants)}, inputs={len(self.inputs)})"
        )

    __repr__ = __str__

    @property
    def project(self) -> Project:
        return self.exploration.project

    @property
    def packages(self) -> list[Package]:
        return self.exploration.packages

    @property
    def modules(self) -> list[Module]:
        return self.exploration.modules

    @property
    def chunks(self) -> list[CodeChunk]:
        return self.exploration.code_chunks

    def statistics(self) -> ProjectStatistics:
        """Return discovery statistics for the project."""
        return project_statistics(self.exploration)

    def mutant_statistics(self, mutants: Optional[Sequence[CodeChunk]] = None) -> MutantStatistics:
        """Return generation and execution statistics for selected or all mutants."""
        return mutant_statistics(list(mutants) if mutants is not None else self.mutants)

    def mutation_score(
        self,
        mutants: Optional[Sequence[CodeChunk]] = None,
        *,
        environment_id: Optional[str] = None,
    ) -> MutationScore:
        """Score selected or all mutants using their related pytest outcomes."""
        selected = list(mutants) if mutants is not None else self.mutants
        if environment_id is None and self.environment is not None:
            environment_id = self.environment.environment_id
        if environment_id is None:
            environment_ids = {output.environment_id for mutant in selected for output in mutant.test_execution_outputs}
            if len(environment_ids) > 1:
                raise ValueError("multiple execution environments are present; select an environment_id")
            environment_id = next(iter(environment_ids), None)
        return mutation_score(selected, environment_id=environment_id)

    @staticmethod
    def operators() -> list[OperatorInfo]:
        """Return the friendly catalogue of implemented mutation operators."""
        return available_operators()

    def find_packages(self, query: str = "*") -> list[Package]:
        """Find packages by ID, dotted name, or relative path."""
        return [package for package in self.packages if _matches(query, package.package_id, package.name, package.path)]

    def find_modules(self, query: str = "*") -> list[Module]:
        """Find modules by ID, dotted name, or relative path."""
        return [module for module in self.modules if _matches(query, module.module_id, module.name, module.path)]

    def find_chunks(self, query: str = "*", *, include_mutants: bool = False) -> list[CodeChunk]:
        """Find chunks by ID, qualified function name, or module/function label."""
        chunks = [*self.chunks, *self.mutants] if include_mutants else self.chunks
        return [
            chunk
            for chunk in chunks
            if _matches(query, chunk.chunk_id, chunk.function_name, f"{chunk.module.name}:{chunk.function_name}")
        ]

    def chunks_with_tests(
        self,
        targets: Optional[Selectable | Sequence[Selectable]] = None,
        *,
        include_mutants: bool = False,
    ) -> list[CodeChunk]:
        """Return chunks under the selected targets that have inferred related tests."""
        selected_targets = self.chunks if targets is None else _as_list(targets)
        for target in selected_targets:
            self._validate_target(target)
        originals = {
            chunk.chunk_id: chunk for target in selected_targets for chunk in self._original_chunks_for(target)
        }
        selected = list(originals.values())
        if include_mutants:
            original_ids = set(originals)
            selected.extend(mutant for mutant in self.mutants if mutant.original_id in original_ids)
        return [chunk for chunk in selected if chunk.related_test_cases]

    def mutate(
        self,
        targets: Selectable | Sequence[Selectable],
        operators: OperatorSelection,
        *,
        max_degree: int = 1,
        show_progress: bool = True,
    ) -> list[CodeChunk]:
        """Generate mutants for one or several selected packages, modules, or chunks."""
        selected_targets = _as_list(targets)
        if not selected_targets:
            raise ValueError("at least one mutation target is required")
        resolved_operators = resolve_operators(operators)
        generated = []
        canonical_by_id = {mutant.chunk_id: mutant for mutant in self.mutants}
        initial_mutant_count = len(canonical_by_id)
        progress_ids = set(canonical_by_id)
        for target in selected_targets:
            self._validate_target(target)
        source_chunks = {
            chunk.chunk_id: chunk for target in selected_targets for chunk in self._original_chunks_for(target)
        }
        progress = _MutationProgress(total_chunks=len(source_chunks), enabled=show_progress)
        processed_chunks = 0

        def report_mutant(mutant: CodeChunk) -> None:
            if mutant.chunk_id not in progress_ids:
                progress_ids.add(mutant.chunk_id)
                progress.update(len(progress_ids) - initial_mutant_count, processed_chunks)

        try:
            for source_index, source_chunk in enumerate(source_chunks.values(), start=1):
                for mutant in generate_mutants(
                    source_chunk,
                    resolved_operators,
                    max_degree,
                    on_mutant=report_mutant,
                ):
                    if mutant.parent_id in canonical_by_id:
                        mutant.parent = canonical_by_id[mutant.parent_id]
                    if mutant.chunk_id in canonical_by_id:
                        _disconnect_duplicate(mutant)
                        continue
                    canonical_by_id[mutant.chunk_id] = mutant
                    self.mutants.append(mutant)
                    generated.append(mutant)
                processed_chunks = source_index
                progress.update(len(generated), processed_chunks)
        finally:
            progress.finish(len(generated), processed_chunks)
        return generated

    def mutate_chunks_with_tests(
        self,
        targets: Optional[Selectable | Sequence[Selectable]],
        operators: OperatorSelection,
        *,
        max_degree: int = 1,
        show_progress: bool = True,
    ) -> list[CodeChunk]:
        """Generate mutants only for selected chunks with inferred related tests."""
        selected = self.chunks_with_tests(targets)
        if not selected:
            return []
        return self.mutate(selected, operators, max_degree=max_degree, show_progress=show_progress)

    def find_mutants(
        self,
        query: str = "*",
        *,
        operator: Optional[str] = None,
        degree: Optional[int] = None,
    ) -> list[CodeChunk]:
        """Filter generated mutants by source/function, operator, and degree."""
        normalized_operator = operator.lower().replace("_", "-") if operator else None
        return [
            mutant
            for mutant in self.mutants
            if _matches(query, mutant.chunk_id, mutant.function_name, mutant.original_id or "")
            and (degree is None or mutant.mutation_degree == degree)
            and (
                normalized_operator is None
                or normalized_operator in (mutant.mutation_operator or "").lower().replace("_", "-")
            )
        ]

    def tests_for(self, chunk: CodeChunk) -> list[TestCase]:
        """Return tests inferred for an original or mutant chunk."""
        self._validate_target(chunk)
        return chunk.related_test_cases

    def add_input(
        self,
        chunk: CodeChunk,
        arguments: tuple,
        *,
        label: Optional[str] = None,
    ) -> FunctionInput:
        """Add trusted positional arguments to an original or mutant chunk."""
        original = self._original_chunk(chunk)
        function_input = FunctionInput.from_value(
            arguments,
            label or f"{original.function_name}{arguments!r}",
            original_chunk=original,
        )
        self._remember_input(function_input)
        return function_input

    def add_text_input(self, chunk: CodeChunk, text: str) -> FunctionInput:
        """Add JSON, literal, or literal-call input to an original or mutant chunk."""
        original = self._original_chunk(chunk)
        function_input = FunctionInput.from_text_representation(text, original_chunk=original)
        self._remember_input(function_input)
        return function_input

    def prepare_environment(
        self,
        *,
        environments_root: Optional[Path] = None,
        refresh_requirements: bool = False,
        show_progress: bool = True,
    ) -> PythonExecutionEnvironment:
        """Create or refresh the reusable Python environment for this project."""
        if show_progress:
            print("Preparing execution environment...", flush=True)
        environment = PythonExecutionEnvironment.for_project(self.project, environments_root)
        environment.prepare(refresh_requirements=refresh_requirements)
        self.environment = environment
        if show_progress:
            print(f"Execution environment ready: {environment.path}", flush=True)
        return environment

    def run_inputs(
        self,
        chunks: Optional[CodeChunk | Sequence[CodeChunk]] = None,
        *,
        timeout_seconds: float = 2.0,
        extra_env: Optional[dict[str, str]] = None,
        show_progress: bool = True,
    ) -> list[ExecutionOutput]:
        """Run all applicable inputs for the selected chunks, preparing the venv if needed."""
        selected = self._execution_chunks(chunks)
        environment = self._prepared_environment(show_progress=show_progress)
        executor = StandalonePythonExecution(timeout_seconds=timeout_seconds)
        progress = _TaskProgress("Executing inputs", len(selected), enabled=show_progress)
        outputs = []
        try:
            for completed, chunk in enumerate(selected, start=1):
                outputs.extend(executor.execute_all(chunk, environment, extra_env=extra_env))
                progress.update(completed, f"{len(outputs)} outputs")
        finally:
            progress.finish()
        self._remember_outputs(self.input_outputs, outputs, "execution_id")
        return outputs

    def run_tests(
        self,
        chunks: Optional[CodeChunk | Sequence[CodeChunk]] = None,
        *,
        parallel: bool = True,
        max_workers: Optional[int] = None,
        timeout_seconds: float = 2.0,
        extra_env: Optional[dict[str, str]] = None,
        show_progress: bool = True,
        fallback_to_full_suite: bool = False,
    ) -> list[TestExecutionOutput]:
        """Run related pytest cases for selected chunks, in parallel by default."""
        selected = self._execution_chunks(chunks)
        environment = self._prepared_environment(show_progress=show_progress)
        progress = _TaskProgress("Executing tests", len(selected), enabled=show_progress)
        if parallel and len(selected) > 1:
            try:
                outputs = ParallelExecution(
                    max_workers=max_workers,
                    timeout_seconds=timeout_seconds,
                ).execute_related_tests(
                    selected,
                    environment,
                    extra_env=extra_env,
                    on_chunk_complete=lambda _chunk, completed, _total: progress.update(completed),
                    fallback_to_full_suite=fallback_to_full_suite,
                )
            finally:
                progress.finish()
        else:
            executor = StandalonePythonExecution(timeout_seconds=timeout_seconds)
            outputs = []
            try:
                for completed, chunk in enumerate(selected, start=1):
                    outputs.extend(
                        executor.execute_related_tests(
                            chunk,
                            environment,
                            extra_env=extra_env,
                            fallback_to_full_suite=fallback_to_full_suite,
                        )
                    )
                    progress.update(completed, f"{len(outputs)} outputs")
            finally:
                progress.finish()
        self._remember_outputs(self.test_outputs, outputs, "execution_id")
        return outputs

    def run_tests_for_chunks_with_tests(
        self,
        chunks: Optional[CodeChunk | Sequence[CodeChunk]] = None,
        *,
        include_mutants: Optional[bool] = None,
        parallel: bool = True,
        max_workers: Optional[int] = None,
        timeout_seconds: float = 2.0,
        extra_env: Optional[dict[str, str]] = None,
        show_progress: bool = True,
    ) -> list[TestExecutionOutput]:
        """Run related pytest cases for chunks that have inferred tests, without full-suite fallback."""
        if chunks is None:
            selected = self.chunks_with_tests(include_mutants=bool(self.mutants) if include_mutants is None else include_mutants)
        else:
            selected = [chunk for chunk in _as_list(chunks) if self.tests_for(chunk)]
        if not selected:
            return []
        return self.run_tests(
            selected,
            parallel=parallel,
            max_workers=max_workers,
            timeout_seconds=timeout_seconds,
            extra_env=extra_env,
            show_progress=show_progress,
            fallback_to_full_suite=False,
        )

    def save(self, session: Session, *, commit: bool = False) -> None:
        """Add the complete known workspace state to a caller-owned SQLAlchemy session."""
        session.add(self.project)
        session.add_all([*self.mutants, *self.inputs, *self.input_outputs, *self.test_outputs])
        if commit:
            session.commit()

    def _validate_target(self, target: Selectable) -> None:
        if isinstance(target, Package):
            belongs = any(target is package for package in self.packages)
        elif isinstance(target, Module):
            belongs = any(target is module for module in self.modules)
        else:
            belongs = any(target is chunk for chunk in [*self.chunks, *self.mutants])
        if not belongs:
            raise ValueError("target does not belong to this mutation workspace")

    def _original_chunks_for(self, target: Selectable) -> list[CodeChunk]:
        if isinstance(target, CodeChunk):
            return [self._original_chunk(target)]
        if isinstance(target, Module):
            return [chunk for chunk in target.code_chunks if chunk.mutation_degree == 0]
        package_ids = {target.package_id}
        pending = list(target.children)
        while pending:
            package = pending.pop()
            if package.package_id in package_ids:
                continue
            package_ids.add(package.package_id)
            pending.extend(package.children)
        return [
            chunk
            for module in self.modules
            if module.package_id in package_ids
            for chunk in module.code_chunks
            if chunk.mutation_degree == 0
        ]

    def _original_chunk(self, chunk: CodeChunk) -> CodeChunk:
        self._validate_target(chunk)
        if chunk.mutation_degree == 0:
            return chunk
        if chunk.original is None:
            raise ValueError("mutant is not connected to its original chunk")
        return chunk.original

    def _remember_input(self, function_input: FunctionInput) -> None:
        if all(existing.input_id != function_input.input_id for existing in self.inputs):
            self.inputs.append(function_input)

    def _execution_chunks(self, chunks: Optional[CodeChunk | Sequence[CodeChunk]]) -> list[CodeChunk]:
        selected = list(self.mutants or self.chunks) if chunks is None else _as_list(chunks)
        for chunk in selected:
            self._validate_target(chunk)
        return list({chunk.chunk_id: chunk for chunk in selected}.values())

    def _prepared_environment(self, *, show_progress: bool) -> PythonExecutionEnvironment:
        if self.environment is None or not self.environment.is_current:
            return self.prepare_environment(show_progress=show_progress)
        return self.environment

    @staticmethod
    def _remember_outputs(target: list, outputs: list, identity_attribute: str) -> None:
        known_ids = {getattr(output, identity_attribute) for output in target}
        target.extend(output for output in outputs if getattr(output, identity_attribute) not in known_ids)


def discover(path: str | Path) -> MutationWorkspace:
    """Discover a Python project and start a high-level mutation workflow."""
    return MutationWorkspace(explore_path(path))


def _as_list(value):
    if isinstance(value, (Package, Module, CodeChunk)):
        return [value]
    return list(value)


def _matches(query: str, *values: str) -> bool:
    normalized = query.strip().lower()
    if not normalized or normalized == "*":
        return True
    if any(character in normalized for character in "*?["):
        return any(fnmatch(value.lower(), normalized) for value in values)
    return any(normalized in value.lower() for value in values)


def _disconnect_duplicate(mutant: CodeChunk) -> None:
    """Remove a regenerated state from the graph while retaining its canonical peer."""
    if mutant.parent is not None and mutant in mutant.parent.children:
        mutant.parent.children.remove(mutant)
    if mutant.original is not None and mutant in mutant.original.derived_chunks:
        mutant.original.derived_chunks.remove(mutant)
    if mutant.module is not None and mutant in mutant.module.code_chunks:
        mutant.module.code_chunks.remove(mutant)
    if mutant.project is not None and mutant in mutant.project.code_chunks:
        mutant.project.code_chunks.remove(mutant)


class _MutationProgress:
    def __init__(self, total_chunks: int, *, enabled: bool) -> None:
        self.total_chunks = total_chunks
        self.enabled = enabled

    def update(self, current: int, processed_chunks: int) -> None:
        if self.enabled:
            print(
                f"\rGenerating mutants: {current} new | chunks processed: {processed_chunks}/{self.total_chunks}",
                end="",
                flush=True,
            )

    def finish(self, current: int, processed_chunks: int) -> None:
        if self.enabled:
            print(f"\rGenerating mutants: {current} new | chunks processed: {processed_chunks}/{self.total_chunks}")


class _TaskProgress:
    def __init__(self, label: str, total: int, *, enabled: bool) -> None:
        self.label = label
        self.total = total
        self.enabled = enabled
        self.current = 0
        self.detail = ""

    def update(self, current: int, detail: str = "") -> None:
        self.current = current
        self.detail = detail
        if self.enabled:
            suffix = f" | {detail}" if detail else ""
            print(f"\r{self.label}: {current}/{self.total}{suffix}", end="", flush=True)

    def finish(self) -> None:
        if self.enabled:
            suffix = f" | {self.detail}" if self.detail else ""
            print(f"\r{self.label}: {self.current}/{self.total}{suffix}")
