from pymut4se.model.code_chunk import CodeChunk
from pymut4se.mutations.python.python_mutation import PythonMutation
import ast
import copy


class _ConstantASTMutation(ast.NodeTransformer):
    def __init__(self):
        self.mutations = []

    def visit_Constant(self, node):
        constant_mutations = [-1, 0, 1, 2, 10]

        for value in constant_mutations:
            if value != node.value:
                self.mutations.append((value, node.lineno, node.col_offset))
        if node.value == True:
            self.mutations.append((False, node.lineno, node.col_offset))
        else:
            self.mutations.append((True, node.lineno, node.col_offset))

        return self.generic_visit(node)
    

class ConstantMutation(PythonMutation):
    def _find_mutation_points(self, parsed_code) -> list:
        generator = _ConstantASTMutation()
        generator.visit(parsed_code)
        return generator.mutations

    def _apply_mutation(self, code: CodeChunk, parsed_code, mutation_point: list) -> list[CodeChunk]:
        mutated_codes = []
        for replacement_value, line, col_offset in mutation_point:
            new_tree = copy.deepcopy(parsed_code)
            for node in ast.walk(new_tree):
                if isinstance(node, ast.Constant) and hasattr(node, "lineno") and node.lineno == line and hasattr(node, "col_offset") and node.col_offset == col_offset:
                    node.value = replacement_value
                    mutateChunk = CodeChunk(
                        ast.unparse(new_tree),
                        code.pl,
                        function_name=code.function_name,
                        mutation_degree=code.mutation_degree + 1,
                        location=code.location,
                        original_code=code.original_code,
                        parent_id=code.chunk_id,
                        line_changed=line,
                        mutation_type="constantReplacement",
                        mutation_operator=type(ast.Constant).__name__,
                        mutation_tool="Standard",
                    )
                    mutated_codes.append(mutateChunk)
        return mutated_codes
