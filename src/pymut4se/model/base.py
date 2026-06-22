from __future__ import annotations

import hashlib

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by all PyMut4SE persistence models."""


def generate_id(identity: str) -> str:
    """Generate the stable SHA-256 identifier used by the domain models."""
    return hashlib.sha256(identity.encode()).hexdigest()
