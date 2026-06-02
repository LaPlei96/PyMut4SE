import ast
import copy
from typing import Dict, List, Optional, Tuple

from pymut4se.model.code_chunk import CodeChunk
from pymut4se.mutations.python.python_mutation import PythonMutation


def _annotation_name(annotation: ast.AST) -> Optional[str]:
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    return None


class _FunctionInfo:
    def __init__(self, params: Dict[str, Tuple[Optional[ast.expr], Optional[str]]], local_vars: Dict[str, str]):
        self.params = params
        self.local_vars = local_vars


def _literal_to_ast(value) -> Optional[ast.AST]:
    if isinstance(value, ast.AST):
        return copy.deepcopy(value)
    if isinstance(value, bool):
        return ast.Constant(value=value)
    if isinstance(value, int):
        return ast.Constant(value=value)
    if isinstance(value, float):
        return ast.Constant(value=value)
    if isinstance(value, str):
        return ast.Constant(value=value)
    if isinstance(value, list):
        return ast.List(elts=[], ctx=ast.Load())
    if isinstance(value, dict):
        return ast.Dict(keys=[], values=[])
    return None


class _OptionalParamVisitor(ast.NodeVisitor):
    def __init__(self, functions: Dict[str, _FunctionInfo], fallback_literals: Dict[str, ast.AST]):
        self.functions = functions
        self.current_function: Optional[str] = None
        self.mutations: List[dict] = []
        self.fallback_literals = fallback_literals

    def visit_FunctionDef(self, node: ast.FunctionDef):
        prev = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = prev

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in self.functions:
                info = self.functions[func_name]
                caller_vars = self.functions.get(self.current_function, _FunctionInfo({}, {})).local_vars if self.current_function else {}
                provided_kw = {kw.arg for kw in node.keywords if kw.arg}
                for kw in node.keywords:
                    if kw.arg and kw.arg in info.params and info.params[kw.arg][0] is not None:
                        self.mutations.append(
                            {
                                "line": node.lineno,
                                "mutation_kind": "remove",
                                "keyword": kw.arg,
                            }
                        )
                for param, (default, annot) in info.params.items():
                    if default is None:
                        continue
                    if param in provided_kw:
                        continue
                    value = self._value_for_param(annot, default, caller_vars)
                    if value is None:
                        continue
                    self.mutations.append(
                        {
                            "line": node.lineno,
                            "mutation_kind": "add",
                            "keyword": param,
                            "value": value,
                        }
                    )
        return self.generic_visit(node)

    def _value_for_param(self, annot: Optional[str], default: Optional[ast.expr], local_vars: Dict[str, str]) -> Optional[ast.expr]:
        if annot == "bool":
            if isinstance(default, ast.Constant) and isinstance(default.value, bool):
                return ast.Constant(value=not default.value)
            return ast.Constant(value=True)

        if annot and annot in local_vars:
            return ast.Name(id=local_vars[annot], ctx=ast.Load())

        fallback = self.fallback_literals.get(annot) or self.fallback_literals.get("__default__")
        if fallback is not None:
            return copy.deepcopy(fallback)
        return None


class OptionalParamMutation(PythonMutation):
    def __init__(self, fallback_literals: Optional[Dict[str, object]] = None):
        self.fallback_literals = self._prepare_fallbacks(fallback_literals or {})

    def _prepare_fallbacks(self, user_fallbacks: Dict[str, object]) -> Dict[str, ast.AST]:
        defaults = {
            "int": _literal_to_ast(0),
            "float": _literal_to_ast(0.0),
            "str": _literal_to_ast(""),
            "list": _literal_to_ast([]),
            "dict": _literal_to_ast({}),
            "__default__": _literal_to_ast({}),
        }
        prepared = {k: v for k, v in defaults.items() if v is not None}
        for key, value in user_fallbacks.items():
            ast_value = _literal_to_ast(value)
            if ast_value is not None:
                prepared[key] = ast_value
        return prepared

    def _find_mutation_points(self, parsed_code) -> list:
        functions = self._collect_functions(parsed_code)
        visitor = _OptionalParamVisitor(functions, self.fallback_literals)
        visitor.visit(parsed_code)
        return visitor.mutations

    def _apply_mutation(self, code: CodeChunk, parsed_code, mutation_point: list) -> list[CodeChunk]:
        mutated_codes: List[CodeChunk] = []
        for mutation in mutation_point:
            new_tree = copy.deepcopy(parsed_code)
            for node in ast.walk(new_tree):
                if not isinstance(node, ast.Call) or not hasattr(node, "lineno"):
                    continue
                if node.lineno != mutation["line"]:
                    continue
                if mutation["mutation_kind"] == "remove":
                    node.keywords = [kw for kw in node.keywords if kw.arg != mutation["keyword"]]
                elif mutation["mutation_kind"] == "add":
                    node.keywords.append(ast.keyword(arg=mutation["keyword"], value=copy.deepcopy(mutation["value"])))
            mutateChunk = CodeChunk(
                ast.unparse(new_tree),
                code.pl,
                mutation_degree=code.mutation_degree + 1,
                function_name=code.function_name,
                location=code.location,
                original_code=code.original_code,
                parent_id=code.chunk_id,
                line_changed=mutation["line"],
                mutation_type="optional_param",
                mutation_operator=mutation["mutation_kind"],
                mutation_tool="Standard",
            )
            mutated_codes.append(mutateChunk)
        return mutated_codes

    def _collect_functions(self, tree: ast.AST) -> Dict[str, _FunctionInfo]:
        functions: Dict[str, _FunctionInfo] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                params: Dict[str, Tuple[Optional[ast.expr], Optional[str]]] = {}
                args = node.args.args
                defaults = node.args.defaults or []
                offset = len(args) - len(defaults)
                for idx, arg in enumerate(args):
                    default = defaults[idx - offset] if idx >= offset else None
                    annot = _annotation_name(arg.annotation) if arg.annotation else None
                    params[arg.arg] = (default, annot)
                local_vars: Dict[str, str] = {}
                for body_node in ast.walk(node):
                    if isinstance(body_node, ast.AnnAssign) and isinstance(body_node.target, ast.Name):
                        var_annot = _annotation_name(body_node.annotation)
                        if var_annot:
                            local_vars[var_annot] = body_node.target.id
                functions[node.name] = _FunctionInfo(params, local_vars)
        return functions
