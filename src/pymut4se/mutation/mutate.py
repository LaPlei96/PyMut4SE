from __future__ import annotations

import ast
from collections.abc import Sequence
from textwrap import dedent
from typing import Type, Union

from pymut4se.model import CodeChunk, Module, Package
from pymut4se.mutation.mutation import Mutation

MutationOperator = Union[Mutation, Type[Mutation]]
MutationTarget = Union[CodeChunk, Module, Package]


def generate_mutants(
    target: MutationTarget,
    mutation_operators: Sequence[MutationOperator],
    max_degree: int,
) -> list[CodeChunk]:
    """Generate mutants for a code chunk, module, or package ORM graph.

    Args:
        target: A chunk, module, or package whose original chunks should mutate.
        mutation_operators: Operator instances or no-argument operator classes.
        max_degree: Highest mutation degree to generate. Values below one produce
            no mutants.

    Returns:
        Unique generated chunks in generation order. Each mutant is connected to
        its parent, module, and project when those relationships are available.

    Relationship collections may lazy-load, so module and package targets should
    remain attached to an open SQLAlchemy session unless their graph is already
    loaded.
    """
    if max_degree < 1:
        return []

    operators = [_normalize_operator(operator) for operator in mutation_operators]
    source_chunks = _resolve_source_chunks(target)
    mutants: list[CodeChunk] = []
    seen_states = {_chunk_state_key(chunk) for chunk in source_chunks}
    current_generation = [chunk for chunk in source_chunks if chunk.mutation_degree < max_degree]

    while current_generation:
        next_generation: list[CodeChunk] = []
        for chunk in current_generation:
            if chunk.mutation_degree >= max_degree:
                continue

            for operator in operators:
                for mutant in operator.mutate(chunk):
                    mutant_state = _chunk_state_key(mutant)
                    if mutant.mutation_degree > max_degree or mutant_state in seen_states:
                        _disconnect_mutant(mutant)
                        continue
                    _connect_mutant(mutant, chunk)
                    seen_states.add(mutant_state)
                    mutants.append(mutant)
                    next_generation.append(mutant)

        current_generation = next_generation

    return mutants


def _normalize_operator(operator: MutationOperator) -> Mutation:
    if isinstance(operator, Mutation):
        return operator
    return operator()


def _resolve_source_chunks(target: MutationTarget) -> list[CodeChunk]:
    if isinstance(target, CodeChunk):
        return [target]
    if isinstance(target, Module):
        return _original_chunks(target.code_chunks)
    return _chunks_for_package(target)


def _chunks_for_package(package: Package) -> list[CodeChunk]:
    chunks = [
        chunk
        for current_package in _package_tree(package)
        for module in current_package.modules
        for chunk in module.code_chunks
    ]
    return _original_chunks(chunks)


def _package_tree(package: Package) -> list[Package]:
    packages = []
    pending = [package]
    seen_ids = set()
    while pending:
        current = pending.pop()
        if current.package_id in seen_ids:
            continue
        seen_ids.add(current.package_id)
        packages.append(current)
        pending.extend(reversed(current.children))
    return packages


def _original_chunks(chunks: Sequence[CodeChunk]) -> list[CodeChunk]:
    return [chunk for chunk in chunks if chunk.mutation_degree == 0]


def _connect_mutant(mutant: CodeChunk, parent: CodeChunk) -> None:
    """Attach a generated mutant to the same ORM aggregate as its parent."""
    mutant.parent = parent
    if parent.module is not None:
        mutant.module = parent.module
    if parent.project is not None:
        mutant.project = parent.project


def _disconnect_mutant(mutant: CodeChunk) -> None:
    """Remove a rejected candidate from relationships populated by its builder."""
    if mutant.parent is not None and mutant in mutant.parent.children:
        mutant.parent.children.remove(mutant)
    if mutant.module is not None and mutant in mutant.module.code_chunks:
        mutant.module.code_chunks.remove(mutant)
    if mutant.project is not None and mutant in mutant.project.code_chunks:
        mutant.project.code_chunks.remove(mutant)
    if mutant.original is not None and mutant in mutant.original.derived_chunks:
        mutant.original.derived_chunks.remove(mutant)


def _chunk_state_key(chunk: CodeChunk) -> str:
    """Return a formatting-independent key for a chunk's Python semantics."""
    try:
        tree = ast.parse(dedent(chunk.code))
    except SyntaxError:
        return chunk.code
    return ast.dump(tree, include_attributes=False)
