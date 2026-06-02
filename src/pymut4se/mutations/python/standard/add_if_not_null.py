from pymut4se.model.code_chunk import CodeChunk
from pymut4se.mutations.python.python_mutation import PythonMutation
import ast
import copy


class _IfNotNullASTMutation(ast.NodeTransformer):
    def __init__(self, variable_name):
        self.mutations = []
        self.variable_name = variable_name
    
    def visit_FunctionDef(self, node):
        new_test = ast.Compare(
            left=ast.Name(id=self.variable_name, ctx=ast.Load()),
            ops=[ast.IsNot()],
            comparators=[ast.Constant(value=None)]
        )
        new_if = ast.If(
            test=new_test,
            body=node.body,
            orelse=[]
        )
        node.body = [new_if]
        self.mutations.append((node, node.lineno)) 
        return self.generic_visit(node)



class IfNotNullMutation(PythonMutation):
    def _find_mutation_points(self, parsed_code) -> list:
        mutated_points = []
        return mutated_points


    def _apply_mutation(self, code: CodeChunk, parsed_code, mutation_point: list) -> list[CodeChunk]:
        mutated_codes = []

        tree = copy.deepcopy(parsed_code)
        function_def = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
        all_params = {arg.arg for arg in function_def.args.args}
        
        for variable in all_params:
            new_tree = copy.deepcopy(tree)
            new_tree = _IfNotNullASTMutation(variable).visit(new_tree)
            
            mutateChunk = CodeChunk(
                ast.unparse(new_tree),
                code.pl,
                function_name=code.function_name,
                mutation_degree=code.mutation_degree + 1,
                location=code.location,
                original_code=code.original_code,
                parent_id=code.chunk_id,
                line_changed=2,
                mutation_type="if_not_null",
                mutation_operator=variable,
                mutation_tool="Standard",
            )
            mutated_codes.append(mutateChunk)
        return mutated_codes
