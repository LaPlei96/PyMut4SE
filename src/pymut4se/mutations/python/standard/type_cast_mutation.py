from pymut4se.model.code_chunk import CodeChunk
from pymut4se.mutations.python.python_mutation import PythonMutation
import ast
import copy


class _TypeCastASTMutation(ast.NodeTransformer):
    def __init__(self, variable_name, cast_type):
        self.mutations = []
        self.variable_name = variable_name
        self.cast_type = cast_type

    
    def visit_FunctionDef(self, node):
        new_assign = ast.Assign(
            targets=[ast.Name(id=self.variable_name, ctx=ast.Store(), lineno=node.lineno, col_offset=node.col_offset)],
            value=ast.Call(
                func=ast.Name(id=self.cast_type, ctx=ast.Load(), lineno=node.lineno, col_offset=node.col_offset),
                args=[ast.Name(id=self.variable_name, ctx=ast.Load(), lineno=node.lineno, col_offset=node.col_offset)],
                keywords=[]
            ),
            lineno=node.lineno,
            col_offset=node.col_offset
        )
        node.body.insert(0, new_assign)
        self.mutations.append((node, node.lineno)) 
        return self.generic_visit(node)



class TypeCastMutation(PythonMutation):
    def _find_mutation_points(self, parsed_code) -> list:
        mutated_points = []
        return mutated_points


    def _apply_mutation(self, code: CodeChunk, parsed_code, mutation_point: list) -> list[CodeChunk]:
        mutated_codes = []
        cast_types = ['int', 'str', 'float'] 

        tree = copy.deepcopy(parsed_code)
        function_def = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
        all_params = {arg.arg for arg in function_def.args.args}
        
        for variable in all_params:
            for cast_type in cast_types:
                new_tree = copy.deepcopy(tree)
                new_tree = _TypeCastASTMutation(variable, cast_type).visit(new_tree)
                
                mutateChunk = CodeChunk(
                    ast.unparse(new_tree),
                    code.pl,
                    function_name=code.function_name,
                    mutation_degree=code.mutation_degree + 1,
                    location=code.location,
                    original_code=code.original_code,
                    parent_id=code.chunk_id,
                    line_changed=2,
                    mutation_type="cast_type",
                    mutation_operator=cast_type,
                    mutation_tool="Standard",
                )
                mutated_codes.append(mutateChunk)
        return mutated_codes
