from datasets.quixbugs.inputs.code.inputs import Inputs
from pymut4se.model.input import ProgramInput as Input


class InputsShortestPath(Inputs):
    def get_inputs(self):
        graph4 = {
            ("A", "B"): 3,
            ("A", "C"): 3,
            ("A", "F"): 5,
            ("C", "B"): -2,
            ("C", "D"): 7,
            ("C", "E"): 4,
            ("D", "E"): -5,
            ("E", "F"): -1,
        }

        graph5 = {
            ("A", "B"): 1,
            ("B", "C"): 2,
            ("C", "D"): 3,
            ("D", "E"): -1,
            ("E", "F"): 4,
        }

        graph6 = {
            ("A", "B"): 1,
            ("B", "C"): 2,
            ("C", "D"): 3,
            ("D", "E"): -1,
            ("E", "D"): 1,
            ("E", "F"): 4,
        }
        return [
            Input.from_value((graph4,), """graph4 = {"A": {"B": 3, "C": 3, "F": 5}, "C": {"B": -2, "D": 7, "E": 4}, "D": {"E": -5}, "E": {"F": -1}}"""),
            Input.from_value((graph5,), """graph5 = {"A": {"B": 1}, "B": {"C": 2}, "C": {"D": 3}, "D": {"E": -1}, "E": {"F": 4}}"""),
            Input.from_value((graph6,), """graph6 = {"A": {"B": 1}, "B": {"C": 2}, "C": {"D": 3}, "D": {"E": -1}, "E": {"D": 1, "F": 4}}"""),
        ]
