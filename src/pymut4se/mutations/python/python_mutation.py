from pymut4se.model.code_chunk import CodeChunk
from pymut4se.mutations.mutation import Mutation

from ast import parse, Module


class PythonMutation(Mutation):
    def _parse(self, code: CodeChunk) -> Module:
        tree = parse(code.code)
        return tree
