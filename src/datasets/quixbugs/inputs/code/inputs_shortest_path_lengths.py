from datasets.quixbugs.inputs.code.inputs import Inputs
from pymut4se.model.input import ProgramInput as Input


class InputsShortestPathLengths(Inputs):
    def get_inputs():
        graph = {
            (0, 2): 3,
            (0, 5): 5,
            (2, 1): -2,
            (2, 3): 7,
            (2, 4): 4,
            (3, 4): -5,
            (4, 5): -1,
        }

        graph1 = {
            (0, 1): 3,
            (1, 2): 5,
            (2, 3): -2,
            (3, 4): 7,
        }

        graph2 = {
            (0, 1): 3,
            (2, 3): 5,
        }

        graph3 = {
            (0, 1): 3,
            (1, 2): 5,
            (2, 0): -1,
        }

        return [
            Input.from_value((graph,), """graph = {0: {2: 3, 5: 5}, 2: {1: -2, 3: 7, 4: 4}, 3: {4: -5}, 4: {5: -1}}"""),
            Input.from_value((graph1,), """graph1 = {0: {1: 3}, 1: {2: 5}, 2: {3: -2}, 3: {4: 7}}"""),
            Input.from_value((graph2,), """graph2 = {0: {1: 3}, 2: {3: 5}}"""),
            Input.from_value((graph3,), """graph3 = {0: {1: 3}, 1: {2: 5}, 2: {0: -1}}"""),
        ]
