from pymut4se.model.code_chunk import CodeChunk
from pymut4se.mutations.python.python_mutation import PythonMutation
import ast
import copy


class _DeleteASTMutation(ast.NodeTransformer):
    def __init__(self):
        self.mutations = []

    def visit_Assign(self, node):
        self.mutations.append((node, node.lineno))
        return self.generic_visit(node)
    
    def visit_AugAssign(self, node):
        self.mutations.append((node, node.lineno))
        return self.generic_visit(node)
    
    def visit_If(self, node):
        self.mutations.append((node, node.lineno))
        return self.generic_visit(node)
    
    def visit_While(self, node):
        self.mutations.append((node, node.lineno))
        return self.generic_visit(node)
    
    def visit_Return(self, node):
        self.mutations.append((node, node.lineno))
        return self.generic_visit(node)
    

class DeleteNode(ast.NodeTransformer): 
    def __init__(self, target_node):
        self.target_node = target_node

    def generic_visit(self, node):
        if node is self.target_node:
            return None  
        return super().generic_visit(node)


class DeleteMutation(PythonMutation):
    def _find_mutation_points(self, parsed_code) -> list:
        generator = _DeleteASTMutation()
        generator.visit(parsed_code)
        return generator.mutations

    def _apply_mutation(self, code: CodeChunk, parsed_code, mutation_point: list) -> list[CodeChunk]:
        mutated_codes = []
        for mutated_node, line in mutation_point:
            new_tree = copy.deepcopy(parsed_code)
            for node in ast.walk(new_tree):
                if isinstance(node, type(mutated_node)) and hasattr(node, "lineno") and node.lineno == line:
                    if isinstance(node, (ast.Assign, ast.AugAssign, ast.If, ast.While, ast.Return)):
                        DeleteNode(node).visit(new_tree)
                        ast.fix_missing_locations(new_tree)
            mutateChunk = CodeChunk(
                ast.unparse(new_tree),
                code.pl,
                function_name=code.function_name,
                mutation_degree=code.mutation_degree + 1,
                location=code.location,
                original_code=code.original_code,
                parent_id=code.chunk_id,
                line_changed=line,
                mutation_type="delete_stmt",
                mutation_operator=type(mutated_node).__name__,
                mutation_tool="Standard",
            )
            mutated_codes.append(mutateChunk)
        return mutated_codes
