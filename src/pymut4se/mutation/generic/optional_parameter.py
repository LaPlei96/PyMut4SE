from __future__ import annotations

import ast
import copy
from dataclasses import dataclass
from typing import Optional

from pymut4se.mutation.generic.utils import build_mutants_from_points
from pymut4se.mutation.mutation import PythonASTMutation
from pymut4se.model.code_chunk import CodeChunk

ParamInfo = tuple[Optional[ast.expr], Optional[str]]


def _annotation_name(annotation: ast.AST) -> Optional[str]:
    """Return a readable name for simple annotations."""
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    if isinstance(annotation, ast.Subscript):
        container_name = _annotation_name(annotation.value)
        if container_name in {"Optional", "Union"}:
            elements = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
            return next(
                (name for element in elements if (name := _annotation_name(element)) not in {None, "None"}),
                None,
            )
        return container_name
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        left_name = _annotation_name(annotation.left)
        return left_name if left_name not in {None, "None"} else _annotation_name(annotation.right)
    return None


@dataclass(frozen=True)
class _FunctionInfo:
    """Defaulted parameters and typed locals available in one function."""

    params: dict[str, ParamInfo]
    positional_params: tuple[str, ...]
    local_vars: dict[str, str]


@dataclass(frozen=True)
class _OptionalParamPoint:
    """A keyword argument mutation at a call site."""

    line: int
    col_offset: int
    mutation_kind: str
    keyword: str
    value: Optional[ast.expr] = None


@dataclass(frozen=True)
class _OptionalDefaultPoint:
    """A default value mutation in a function declaration."""

    line: int
    col_offset: int
    parameter_name: str
    parameter_kind: str
    value: ast.expr


def _literal_to_ast(value: object) -> Optional[ast.expr]:
    """Convert common Python literals into AST literals."""
    if isinstance(value, ast.expr):
        return copy.deepcopy(value)
    if value is None or isinstance(value, (bool, int, float, str, list, dict, tuple)):
        try:
            return ast.parse(repr(value), mode="eval").body
        except (SyntaxError, ValueError):
            return None
    return None


class _LocalVariableVisitor(ast.NodeVisitor):
    """Collect annotated locals without descending into nested functions."""

    def __init__(self):
        self.local_vars: dict[str, str] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return None

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            annotation = _annotation_name(node.annotation)
            if annotation:
                self.local_vars[annotation] = node.target.id


class _OptionalParamVisitor(ast.NodeVisitor):
    """Find calls where optional keyword arguments can be added or removed."""

    def __init__(self, functions: dict[str, _FunctionInfo], fallback_literals: dict[str, ast.expr]):
        self.functions = functions
        self.current_function: Optional[str] = None
        self.mutations: list[_OptionalParamPoint] = []
        self.fallback_literals = fallback_literals

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        prev = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = prev

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in self.functions:
                info = self.functions[func_name]
                caller_info = self.functions.get(self.current_function) if self.current_function else None
                caller_vars = caller_info.local_vars if caller_info else {}
                provided_kw = {kw.arg for kw in node.keywords if kw.arg}
                supplied_positionally = set(info.positional_params[: len(node.args)])
                has_expansion = any(isinstance(argument, ast.Starred) for argument in node.args) or any(
                    keyword.arg is None for keyword in node.keywords
                )
                for kw in node.keywords:
                    if kw.arg and kw.arg in info.params and info.params[kw.arg][0] is not None:
                        self.mutations.append(
                            _OptionalParamPoint(
                                line=node.lineno,
                                col_offset=node.col_offset,
                                mutation_kind="remove",
                                keyword=kw.arg,
                            )
                        )
                for param, (default, annot) in info.params.items():
                    if default is None:
                        continue
                    if param in provided_kw or param in supplied_positionally or has_expansion:
                        continue
                    value = self._value_for_param(annot, default, caller_vars)
                    if value is None:
                        continue
                    self.mutations.append(
                        _OptionalParamPoint(
                            line=node.lineno,
                            col_offset=node.col_offset,
                            mutation_kind="add",
                            keyword=param,
                            value=value,
                        )
                    )
        return self.generic_visit(node)

    def _value_for_param(
        self,
        annot: Optional[str],
        default: Optional[ast.expr],
        local_vars: dict[str, str],
    ) -> Optional[ast.expr]:
        return _replacement_value(annot, default, self.fallback_literals, local_vars)


def _replacement_value(
    annotation: Optional[str],
    default: Optional[ast.expr],
    fallback_literals: dict[str, ast.expr],
    local_vars: Optional[dict[str, str]] = None,
) -> Optional[ast.expr]:
    """Choose a non-default value compatible with an annotation when possible."""
    if annotation == "bool":
        if isinstance(default, ast.Constant) and isinstance(default.value, bool):
            return ast.Constant(value=not default.value)
        return ast.Constant(value=True)

    if annotation and local_vars and annotation in local_vars:
        return ast.Name(id=local_vars[annotation], ctx=ast.Load())

    fallback = fallback_literals.get(annotation) if annotation is not None else None
    fallback = fallback or fallback_literals.get("__default__")
    if fallback is not None:
        return _ensure_different(copy.deepcopy(fallback), default)
    return None


def _ensure_different(value: ast.expr, default: Optional[ast.expr]) -> ast.expr:
    """Avoid producing a semantically identical explicit default argument."""
    if default is None or ast.dump(value, include_attributes=False) != ast.dump(default, include_attributes=False):
        return value
    if isinstance(value, ast.Constant):
        if isinstance(value.value, bool):
            return ast.Constant(value=not value.value)
        if isinstance(value.value, (int, float)):
            return ast.Constant(value=value.value + 1)
        if isinstance(value.value, str):
            return ast.Constant(value=f"{value.value}mutated")
    if isinstance(value, ast.List):
        return ast.List(elts=[ast.Constant(value=None)], ctx=ast.Load())
    if isinstance(value, ast.Dict):
        return ast.Dict(keys=[ast.Constant(value="mutated")], values=[ast.Constant(value=None)])
    return value


def _prepare_fallbacks(user_fallbacks: dict[str, object]) -> dict[str, ast.expr]:
    """Prepare AST values used when no local value matches an annotation."""
    defaults = {
        "int": _literal_to_ast(0),
        "float": _literal_to_ast(0.0),
        "str": _literal_to_ast(""),
        "list": _literal_to_ast([]),
        "dict": _literal_to_ast({}),
        "__default__": _literal_to_ast({}),
    }
    prepared = {key: value for key, value in defaults.items() if value is not None}
    for key, value in user_fallbacks.items():
        ast_value = _literal_to_ast(value)
        if ast_value is not None:
            prepared[key] = ast_value
    return prepared


class OptionalParamCallerMutation(PythonASTMutation):
    """Add or remove optional keyword arguments at same-module function calls."""

    def __init__(self, fallback_literals: Optional[dict[str, object]] = None):
        self.fallback_literals = _prepare_fallbacks(fallback_literals or {})
        self._module_functions: dict[str, _FunctionInfo] = {}

    def mutate(self, code: CodeChunk) -> list[CodeChunk]:
        """Mutate calls using signatures from the chunk's original module graph."""
        self._module_functions = {}
        if code.module is not None:
            for sibling in code.module.code_chunks:
                if sibling.mutation_degree != 0 or sibling.chunk_id == code.chunk_id:
                    continue
                self._module_functions.update(self._collect_functions(self._parse(sibling)))
        try:
            return super().mutate(code)
        finally:
            self._module_functions = {}

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_OptionalParamPoint]:
        functions = {**self._module_functions, **self._collect_functions(parsed_code)}
        visitor = _OptionalParamVisitor(functions, self.fallback_literals)
        visitor.visit(parsed_code)
        return visitor.mutations

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_OptionalParamPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="optional_param_caller",
            mutation_operator=lambda point: f"{point.mutation_kind}:{point.keyword}",
            apply_mutation=_apply_optional_param_mutation,
        )

    def _collect_functions(self, tree: ast.AST) -> dict[str, _FunctionInfo]:
        functions: dict[str, _FunctionInfo] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params: dict[str, ParamInfo] = {}
                args = [*node.args.posonlyargs, *node.args.args]
                defaults = node.args.defaults or []
                offset = len(args) - len(defaults)
                for idx, arg in enumerate(args):
                    default = defaults[idx - offset] if idx >= offset else None
                    annot = _annotation_name(arg.annotation) if arg.annotation else None
                    params[arg.arg] = (default, annot)
                for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
                    annotation = _annotation_name(arg.annotation) if arg.annotation else None
                    params[arg.arg] = (default, annotation)
                local_visitor = _LocalVariableVisitor()
                for statement in node.body:
                    local_visitor.visit(statement)
                functions[node.name] = _FunctionInfo(
                    params=params,
                    positional_params=tuple(argument.arg for argument in args),
                    local_vars=local_visitor.local_vars,
                )
        return functions


class OptionalParamCalleeMutation(PythonASTMutation):
    """Replace optional defaults in the callee's function declaration."""

    def __init__(self, fallback_literals: Optional[dict[str, object]] = None):
        self.fallback_literals = _prepare_fallbacks(fallback_literals or {})

    def _find_mutation_points(self, parsed_code: ast.AST) -> list[_OptionalDefaultPoint]:
        function = next(
            (node for node in ast.walk(parsed_code) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))),
            None,
        )
        if function is None:
            return []

        points: list[_OptionalDefaultPoint] = []
        positional_args = [*function.args.posonlyargs, *function.args.args]
        default_offset = len(positional_args) - len(function.args.defaults)
        for index, default in enumerate(function.args.defaults):
            argument = positional_args[default_offset + index]
            if argument.arg in {"self", "cls"}:
                continue
            annotation = _annotation_name(argument.annotation) if argument.annotation else None
            replacement = _replacement_value(annotation, default, self.fallback_literals)
            if replacement is not None:
                points.append(
                    _OptionalDefaultPoint(
                        line=default.lineno,
                        col_offset=default.col_offset,
                        parameter_name=argument.arg,
                        parameter_kind="positional",
                        value=replacement,
                    )
                )

        for argument, default in zip(function.args.kwonlyargs, function.args.kw_defaults, strict=True):
            if default is None or argument.arg in {"self", "cls"}:
                continue
            annotation = _annotation_name(argument.annotation) if argument.annotation else None
            replacement = _replacement_value(annotation, default, self.fallback_literals)
            if replacement is not None:
                points.append(
                    _OptionalDefaultPoint(
                        line=default.lineno,
                        col_offset=default.col_offset,
                        parameter_name=argument.arg,
                        parameter_kind="keyword_only",
                        value=replacement,
                    )
                )
        return points

    def _apply_mutation(
        self,
        code: CodeChunk,
        parsed_code: ast.AST,
        mutation_point: list[_OptionalDefaultPoint],
    ) -> list[CodeChunk]:
        return build_mutants_from_points(
            original=code,
            parsed_code=parsed_code,
            mutation_points=mutation_point,
            mutation_type="optional_param_callee",
            mutation_operator=lambda point: f"replace_default:{point.parameter_name}",
            apply_mutation=_apply_optional_default_mutation,
        )


def _apply_optional_param_mutation(tree: ast.AST, point: _OptionalParamPoint) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_same_call(node, point):
            continue
        if point.mutation_kind == "remove":
            node.keywords = [kw for kw in node.keywords if kw.arg != point.keyword]
        elif point.mutation_kind == "add" and point.value is not None:
            node.keywords.append(ast.keyword(arg=point.keyword, value=copy.deepcopy(point.value)))


def _apply_optional_default_mutation(tree: ast.AST, point: _OptionalDefaultPoint) -> None:
    function = next(
        (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))),
        None,
    )
    if function is None:
        return
    if point.parameter_kind == "positional":
        positional_args = [*function.args.posonlyargs, *function.args.args]
        default_offset = len(positional_args) - len(function.args.defaults)
        for index, argument in enumerate(positional_args[default_offset:]):
            if argument.arg == point.parameter_name:
                function.args.defaults[index] = copy.deepcopy(point.value)
                return
    for index, argument in enumerate(function.args.kwonlyargs):
        if argument.arg == point.parameter_name:
            function.args.kw_defaults[index] = copy.deepcopy(point.value)
            return


def _is_same_call(node: ast.AST, point: _OptionalParamPoint) -> bool:
    return (
        isinstance(node, ast.Call)
        and getattr(node, "lineno", None) == point.line
        and getattr(node, "col_offset", None) == point.col_offset
    )
