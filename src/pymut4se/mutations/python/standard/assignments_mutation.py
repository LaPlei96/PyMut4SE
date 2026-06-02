from pymut4se.model.code_chunk import CodeChunk
from pymut4se.mutations.python.python_mutation import PythonMutation
import ast
import copy


class _AssignmentASTMutation(ast.NodeTransformer):
    def __init__(self):
        self.mutations = []

    def visit_Assign(self, node):
        constant_mutations = [ast.Constant(-1),ast.Constant(0),ast.Constant(1),ast.Constant(2)]
        for mutation in constant_mutations:
            mutated_node = copy.deepcopy(node)
            mutated_node.value = mutation
            self.mutations.append((mutated_node, node.lineno))
        return self.generic_visit(node)
    
    def visit_AugAssign(self, node):
        constant_mutations = [ast.Constant(-1),ast.Constant(0),ast.Constant(1),ast.Constant(2)]
        for mutation in constant_mutations:
            mutated_node = copy.deepcopy(node)
            mutated_node.value = mutation
            self.mutations.append((mutated_node, node.lineno))
        return self.generic_visit(node)


class AssignmentMutation(PythonMutation):
    def _find_mutation_points(self, parsed_code) -> list:
        generator = _AssignmentASTMutation()
        generator.visit(parsed_code)
        return generator.mutations

    def _apply_mutation(self, code: CodeChunk, parsed_code, mutation_point: list) -> list[CodeChunk]:
        mutated_codes = []
        for mutated_node, line in mutation_point:
            new_tree = copy.deepcopy(parsed_code)
            for node in ast.walk(new_tree):
                if isinstance(node, type(mutated_node)) and hasattr(node, "lineno") and node.lineno == line:
                    if isinstance(node, (ast.Assign, ast.AugAssign)):
                        node.value = mutated_node.value
            mutateChunk = CodeChunk(
                ast.unparse(new_tree),
                code.pl,
                function_name=code.function_name,
                mutation_degree=code.mutation_degree + 1,
                location=code.location,
                original_code=code.original_code,
                parent_id=code.chunk_id,
                line_changed=line,
                mutation_type="assignment",
                mutation_operator=type(mutated_node).__name__,
                mutation_tool="Standard",
            )
            mutated_codes.append(mutateChunk)
        return mutated_codes
