from __future__ import annotations

import hashlib
from typing import ClassVar

from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by all PyMut4SE persistence models."""

    _display_fields: ClassVar[tuple[str, ...]] = (
        "name",
        "function_name",
        "path",
        "mutation_degree",
        "mutation_type",
        "mutation_operator",
        "specification",
        "type",
        "text_representation",
        "evidence",
        "confidence",
        "success",
        "return_code",
        "time_taken",
    )

    def __repr__(self) -> str:
        """Return a compact representation safe for notebook collections."""
        values = []
        for field in self._display_fields:
            if field not in self.__dict__:
                continue
            value = self.__dict__[field]
            if value is None or value == "":
                continue
            values.append(f"{field}={_short_value(value)}")
            if len(values) == 3:
                break

        state = inspect(self)
        identity = state.identity
        if identity is not None:
            identifier = identity[0] if len(identity) == 1 else identity
            values.append(f"id={_short_identifier(identifier)!r}")
        else:
            primary_keys = state.mapper.primary_key
            identifier = self.__dict__.get(primary_keys[0].key) if len(primary_keys) == 1 else None
            if identifier:
                values.append(f"id={_short_identifier(identifier)!r}")
        return f"{type(self).__name__}({', '.join(values)})"

    __str__ = __repr__


def generate_id(identity: str) -> str:
    """Generate the stable SHA-256 identifier used by the domain models."""
    return hashlib.sha256(identity.encode()).hexdigest()


def _short_identifier(value: object) -> str:
    text = str(value)
    return f"{text[:8]}…" if len(text) > 9 else text


def _short_value(value: object) -> str:
    if isinstance(value, str) and len(value) > 48:
        return repr(f"{value[:45]}…")
    text = repr(value)
    return text
