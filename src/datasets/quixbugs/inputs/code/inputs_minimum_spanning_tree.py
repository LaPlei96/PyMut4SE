from datasets.quixbugs.inputs.code.inputs import Inputs
from pymut4se.model.input import ProgramInput as Input


class InputsMinimumSpanningTree(Inputs):
    def get_inputs():
        return [
            Input.from_value(value= (
                {
                    (1, 2): 10,
                    (2, 3): 15,
                    (3, 4): 10,
                    (1, 4): 10,
                },
            ), text_representation="""(
                {
                    (1, 2): 10,
                    (2, 3): 15,
                    (3, 4): 10,
                    (1, 4): 10,
                }
            )"""),
            Input.from_value((
                {
                    (1, 2): 6,
                    (1, 3): 1,
                    (1, 4): 5,
                    (2, 3): 5,
                    (2, 5): 3,
                    (3, 4): 5,
                    (3, 5): 6,
                    (3, 6): 4,
                    (4, 6): 2,
                    (5, 6): 6,
                },
            ), """(
                {
                    (1, 2): 6,
                    (1, 3): 1,
                    (1, 4): 5,
                    (2, 3): 5,
                    (2, 5): 3,
                    (3, 4): 5,
                    (3, 5): 6,
                    (3, 6): 4,
                    (4, 6): 2,
                    (5, 6): 6,
                }
            )"""),
            Input.from_value((
                {
                    (1, 2): 6,
                    (1, 3): 1,
                    (2, 4): 2,
                },
            ), """(
                {
                    (1, 2): 6,
                    (1, 3): 1,
                    (2, 4): 2,
                }
            )""")
        ]
