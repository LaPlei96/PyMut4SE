from datasets.quixbugs.inputs.code.inputs import Inputs
from datasets.quixbugs.src.node import Node
from pymut4se.model.input import ProgramInput as Input


class InputsDepthFirstSearch(Inputs):
    def get_inputs():
        return [
            Input.from_value((Node("F"), Node("F")), "(Node(\"F\"), Node(\"F\"))"),
            Input.from_value((
                Node("Tottenham Court Road", None, [Node("London Bridge"), Node("Trafalgar Square")]),
                Node("Westminster"),
            ), "(Node(\"Tottenham Court Road\", None, [Node(\"London Bridge\"), Node(\"Trafalgar Square\")]), Node(\"Westminster\"))"),
        ]
