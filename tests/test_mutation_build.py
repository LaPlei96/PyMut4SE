from collections.abc import Callable
from typing import cast

import pytest

from pymut4se.model import CodeChunk, Module
from pymut4se.mutation import build_mutant, build_mutated_code_chunk


def test_builds_complete_module_source_with_a_substituted_chunk() -> None:
    source = "import math\n\ndef value():\n    return 1\n\ndef unchanged():\n    return math.pi\n"
    module = Module("example", "example.py", source=source)
    original = CodeChunk("def value():\n    return 1\n", module.module_id, "value", "function", 3, 4)
    module.code_chunks.append(original)
    mutant = build_mutated_code_chunk(original, "def value():\n    return 2", 2, 4, "return", "replace")

    rendered = build_mutant(mutant)

    assert "return 2" in rendered
    assert "def unchanged():" in rendered
    assert "return math.pi" in rendered
    assert module.source == source
    namespace: dict[str, object] = {}
    exec(rendered, namespace)
    value = namespace["value"]
    assert callable(value)
    assert cast(Callable[[], int], value)() == 2


def test_reindents_an_unparsed_method_chunk() -> None:
    source = "class Service:\n    def value(self):\n        return 1\n\nsentinel = 3\n"
    module = Module("example", "example.py", source=source)
    original = CodeChunk(
        "    def value(self):\n        return 1\n",
        module.module_id,
        "Service.value",
        "function",
        2,
        3,
    )
    module.code_chunks.append(original)
    mutant = build_mutated_code_chunk(original, "def value(self):\n    return 2", 2, 4, "return", "replace")

    rendered = build_mutant(mutant)

    compile(rendered, "<method-mutant>", "exec")
    assert "    def value(self):\n        return 2" in rendered
    assert "sentinel = 3" in rendered


def test_higher_order_mutants_replace_the_degree_zero_ancestor_range() -> None:
    source = "def first():\n    return 1\ndef second():\n    return 2\n"
    module = Module("example", "example.py", source=source)
    original = CodeChunk("def first():\n    return 1\n", module.module_id, "first", "function", 1, 2)
    module.code_chunks.append(original)
    first_degree = build_mutated_code_chunk(
        original,
        "def first():\n    marker = 1\n    return 2",
        2,
        4,
        "return",
        "first",
    )
    second_degree = build_mutated_code_chunk(
        first_degree,
        "def first():\n    marker = 2\n    extra = True\n    return 3",
        2,
        4,
        "return",
        "second",
    )

    rendered = build_mutant(second_degree)

    assert "marker = 2" in rendered
    assert "extra = True" in rendered
    assert "def second():\n    return 2" in rendered
    compile(rendered, "<higher-order-mutant>", "exec")


def test_preserves_crlf_and_eof_newline_behavior() -> None:
    crlf_source = "def value():\r\n    return 1\r\nsentinel = 3\r\n"
    crlf_module = Module("crlf", "crlf.py", source=crlf_source)
    crlf_original = CodeChunk("def value():\r\n    return 1\r\n", crlf_module.module_id, "value", "function", 1, 2)
    crlf_module.code_chunks.append(crlf_original)
    crlf_mutant = build_mutated_code_chunk(crlf_original, "def value():\n    return 2", 2, 4, "return", "replace")

    rendered_crlf = build_mutant(crlf_mutant)

    assert "\n" not in rendered_crlf.replace("\r\n", "")

    eof_source = "def value():\n    return 1"
    eof_module = Module("eof", "eof.py", source=eof_source)
    eof_original = CodeChunk("def value():\n    return 1", eof_module.module_id, "value", "function", 1, 2)
    eof_module.code_chunks.append(eof_original)
    eof_mutant = build_mutated_code_chunk(eof_original, "def value():\n    return 2", 2, 4, "return", "replace")

    assert not build_mutant(eof_mutant).endswith(("\n", "\r"))


def test_building_an_original_chunk_reproduces_its_module() -> None:
    source = "def value():\n    return 1\n"
    module = Module("example", "example.py", source=source)
    original = CodeChunk(source, module.module_id, "value", "function", 1, 2)
    module.code_chunks.append(original)

    assert build_mutant(original) == source


def test_requires_module_source_and_valid_original_boundaries() -> None:
    detached = CodeChunk("def value(): pass", "module", "value", "function", 1, 1)
    with pytest.raises(ValueError, match="attached to a module"):
        build_mutant(detached)

    empty_module = Module("empty", "empty.py")
    without_source = CodeChunk("def value(): pass", empty_module.module_id, "value", "function", 1, 1)
    empty_module.code_chunks.append(without_source)
    with pytest.raises(ValueError, match="module must contain source"):
        build_mutant(without_source)

    short_module = Module("short", "short.py", source="value = 1\n")
    outside_source = CodeChunk("def value():\n    return 1", short_module.module_id, "value", "function", 1, 2)
    short_module.code_chunks.append(outside_source)
    with pytest.raises(ValueError, match="fall outside the module source"):
        build_mutant(outside_source)
