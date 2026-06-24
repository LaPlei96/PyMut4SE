"""Friendly, workflow-oriented entry points for PyMut4SE."""

from pymut4se.api.operators import OPERATOR_REGISTRY, OperatorInfo, available_operators
from pymut4se.api.statistics import MutantStatistics, MutationScore, ProjectStatistics
from pymut4se.api.workspace import MutationWorkspace, discover

__all__ = [
    "MutantStatistics",
    "MutationScore",
    "MutationWorkspace",
    "OPERATOR_REGISTRY",
    "OperatorInfo",
    "ProjectStatistics",
    "available_operators",
    "discover",
]
