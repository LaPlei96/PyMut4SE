from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from typing import TypeAlias

from pymut4se.mutation import Mutation, MutationOperator
from pymut4se.mutation.generic import (
    ArithmeticMutation,
    BooleanReplacementMutation,
    ConstantReplacementMutation,
    ControlReplacementMutation,
    DeleteAssignmentMutation,
    DeleteDecoratorMutation,
    DeleteIfStatementMutation,
    DeleteReturnMutation,
    DeleteWhileMutation,
    IfNotNullMutation,
    LogicalConnectorMutation,
    OptionalParamCalleeMutation,
    OptionalParamCallerMutation,
    RelationalMutation,
    ReturnPassMutation,
    SwapArgumentsMutation,
    TypeCastMutation,
    UnaryMutation,
)


@dataclass(frozen=True)
class OperatorInfo:
    """User-facing description of an available mutation operator."""

    name: str
    operator_class: type[Mutation]
    description: str

    @property
    def class_name(self) -> str:
        return self.operator_class.__name__

    def __str__(self) -> str:
        return f"{self.name}: {self.description}"

    def __repr__(self) -> str:
        return f"OperatorInfo(name={self.name!r}, class_name={self.class_name!r})"


OperatorReference: TypeAlias = str | MutationOperator | OperatorInfo
OperatorSelection: TypeAlias = OperatorReference | Sequence[OperatorReference]


_OPERATORS = (
    OperatorInfo("add-if-not-null", IfNotNullMutation, "Guard a function body so it only runs for non-null inputs."),
    OperatorInfo("arithmetic", ArithmeticMutation, "Replace one arithmetic binary operator."),
    OperatorInfo("boolean-replacement", BooleanReplacementMutation, "Invert one boolean literal."),
    OperatorInfo("constant-replacement", ConstantReplacementMutation, "Transform one numeric constant."),
    OperatorInfo("control-replacement", ControlReplacementMutation, "Swap break and continue."),
    OperatorInfo("delete-assignment", DeleteAssignmentMutation, "Delete one assignment statement."),
    OperatorInfo("delete-decorator", DeleteDecoratorMutation, "Delete one function decorator."),
    OperatorInfo("delete-if-statement", DeleteIfStatementMutation, "Delete one complete if statement."),
    OperatorInfo("delete-return", DeleteReturnMutation, "Delete one return statement."),
    OperatorInfo("delete-while", DeleteWhileMutation, "Delete one complete while loop."),
    OperatorInfo("logical-connector", LogicalConnectorMutation, "Swap and and or in one boolean expression."),
    OperatorInfo(
        "optional-parameter-callee",
        OptionalParamCalleeMutation,
        "Change an optional parameter default in the called function.",
    ),
    OperatorInfo(
        "optional-parameter-caller",
        OptionalParamCallerMutation,
        "Add, remove, or replace an optional argument at a call site.",
    ),
    OperatorInfo("relational", RelationalMutation, "Replace one comparison operator."),
    OperatorInfo("return-pass", ReturnPassMutation, "Replace a function body with pass."),
    OperatorInfo("swap-arguments", SwapArgumentsMutation, "Swap a pair of positional call arguments."),
    OperatorInfo("type-cast", TypeCastMutation, "Wrap a parameter use in another built-in type cast."),
    OperatorInfo("unary", UnaryMutation, "Replace one unary operator."),
)

OPERATOR_REGISTRY = {operator.name: operator for operator in _OPERATORS}


def available_operators() -> list[OperatorInfo]:
    """Return the implemented operators in stable alphabetical order."""
    return list(_OPERATORS)


def resolve_operators(operators: OperatorSelection) -> list[MutationOperator]:
    """Resolve friendly operator names while preserving supplied classes and instances."""
    if isinstance(operators, str):
        normalized = _normalize_name(operators)
        if normalized in {"all", "*"}:
            return [operator.operator_class for operator in _OPERATORS]
        selected: Sequence[OperatorReference] = [operators]
    elif isinstance(operators, (Mutation, type, OperatorInfo)):
        selected = [operators]
    else:
        selected = operators

    resolved: list[MutationOperator] = []
    for operator in selected:
        if isinstance(operator, OperatorInfo):
            resolved.append(operator.operator_class)
            continue
        if isinstance(operator, Mutation):
            resolved.append(operator)
            continue
        if isinstance(operator, type) and issubclass(operator, Mutation):
            resolved.append(operator)
            continue
        if not isinstance(operator, str):
            raise TypeError("operators must be friendly names, OperatorInfo values, or Mutation classes/instances")
        normalized = _normalize_name(operator)
        try:
            resolved.append(OPERATOR_REGISTRY[normalized].operator_class)
        except KeyError as error:
            choices = ", ".join(OPERATOR_REGISTRY)
            msg = f"unknown mutation operator {operator!r}; choose one of: {choices}"
            raise ValueError(msg) from error
    if not resolved:
        raise ValueError("at least one mutation operator is required")
    return resolved


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace(" ", "-")
