from __future__ import annotations

from textwrap import dedent

from pymut4se.model import CodeChunk


def build_mutant(code_chunk: CodeChunk) -> str:
    """Render a module with one original chunk replaced by the supplied chunk.

    Args:
        code_chunk: Original or mutated chunk attached to a module with source.

    Returns:
        Complete module source containing the supplied chunk's code.

    Raises:
        ValueError: If the chunk has no module, the module has no source, or the
            original chunk boundaries fall outside the module source.

    For higher-order mutants, the degree-zero ancestor defines the source range
    being replaced. This prevents a mutant's changed line count from consuming
    code that follows the original chunk.
    """
    source_chunk = _original_ancestor(code_chunk)
    module = code_chunk.module or source_chunk.module
    if module is None:
        msg = "code_chunk must be attached to a module"
        raise ValueError(msg)
    if module.source is None:
        msg = "code_chunk module must contain source"
        raise ValueError(msg)

    source_lines = module.source.splitlines(keepends=True)
    if source_chunk.start_line < 1 or source_chunk.end_line > len(source_lines):
        msg = "original code chunk lines fall outside the module source"
        raise ValueError(msg)

    start_index = source_chunk.start_line - 1
    end_index = source_chunk.end_line
    original_segment = "".join(source_lines[start_index:end_index])
    indentation = _leading_indentation(source_lines[start_index])
    newline = _newline_style(module.source)
    replacement = _indent_code(code_chunk.code, indentation, newline)
    if _has_trailing_newline(original_segment):
        replacement += newline

    return "".join((*source_lines[:start_index], replacement, *source_lines[end_index:]))


def _original_ancestor(code_chunk: CodeChunk) -> CodeChunk:
    if code_chunk.original is not None:
        return code_chunk.original
    return code_chunk


def _indent_code(code: str, indentation: str, newline: str) -> str:
    lines = dedent(code).splitlines()
    return newline.join(f"{indentation}{line}" if line else "" for line in lines)


def _leading_indentation(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _newline_style(source: str) -> str:
    if "\r\n" in source:
        return "\r\n"
    if "\n" in source:
        return "\n"
    if "\r" in source:
        return "\r"
    return "\n"


def _has_trailing_newline(value: str) -> bool:
    return value.endswith(("\r\n", "\n", "\r"))
