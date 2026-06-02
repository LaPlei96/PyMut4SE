from datasets.quixbugs.inputs.code.inputs import Inputs
from datasets.quixbugs.src.node import Node
from pymut4se.model.input import ProgramInput as Input


class InputsShortestPathLength(Inputs):
    def get_inputs():
        pnode1 = Node("1")
        pnode5 = Node("5")
        pnode4 = Node("4", None, [pnode5])
        pnode3 = Node("3", None, [pnode4])
        pnode2 = Node("2", None, [pnode1, pnode3, pnode4])
        pnode0 = Node("0", None, [pnode2, pnode5])

        length_by_edge = {
            (pnode0, pnode2): 3,
            (pnode0, pnode5): 10,
            (pnode2, pnode1): 1,
            (pnode2, pnode3): 2,
            (pnode2, pnode4): 4,
            (pnode3, pnode4): 1,
            (pnode4, pnode5): 1,
        }
        return [
            Input.from_value((length_by_edge, pnode0, pnode1), """
            pnode1 = Node("1")
            pnode5 = Node("5")
            pnode4 = Node("4", None, [pnode5])
            pnode3 = Node("3", None, [pnode4])
            pnode2 = Node("2", None, [pnode1, pnode3, pnode4])
            pnode0 = Node("0", None, [pnode2, pnode5])
            length_by_edge = {(pnode0, pnode2): 3,
            (pnode0, pnode5): 10,
            (pnode2, pnode1): 1,
            (pnode2, pnode3): 2,
            (pnode2, pnode4): 4,
            (pnode3, pnode4): 1,
            (pnode4, pnode5): 1,}
        return (length_by_edge, pnode0, pnode1)"""),
            Input.from_value((length_by_edge, pnode0, pnode5), """
            pnode1 = Node("1")
            pnode5 = Node("5")
            pnode4 = Node("4", None, [pnode5])
            pnode3 = Node("3", None, [pnode4])
            pnode2 = Node("2", None, [pnode1, pnode3, pnode4])
            pnode0 = Node("0", None, [pnode2, pnode5])
            length_by_edge = {(pnode0, pnode2): 3,
            (pnode0, pnode5): 10,
            (pnode2, pnode1): 1,
            (pnode2, pnode3): 2,
            (pnode2, pnode4): 4,
            (pnode3, pnode4): 1,
            (pnode4, pnode5): 1,}
        return (length_by_edge, pnode0, pnode5)"""),
            Input.from_value((length_by_edge, pnode2, pnode2), """
            pnode1 = Node("1")
            pnode5 = Node("5")
            pnode4 = Node("4", None, [pnode5])
            pnode3 = Node("3", None, [pnode4])
            pnode2 = Node("2", None, [pnode1, pnode3, pnode4])
            pnode0 = Node("0", None, [pnode2, pnode5])
            length_by_edge = {(pnode0, pnode2): 3,
            (pnode0, pnode5): 10,
            (pnode2, pnode1): 1,
            (pnode2, pnode3): 2,
            (pnode2, pnode4): 4,
            (pnode3, pnode4): 1,
            (pnode4, pnode5): 1,}
            return (length_by_edge, pnode2, pnode2)"""),
            Input.from_value((length_by_edge, pnode1, pnode5), """
            pnode1 = Node("1")
            pnode5 = Node("5")
            pnode4 = Node("4", None, [pnode5])
            pnode3 = Node("3", None, [pnode4])
            pnode2 = Node("2", None, [pnode1, pnode3, pnode4])
            pnode0 = Node("0", None, [pnode2, pnode5])
            length_by_edge = {(pnode0, pnode2): 3,
            (pnode0, pnode5): 10,
            (pnode2, pnode1): 1,
            (pnode2, pnode3): 2,
            (pnode2, pnode4): 4,
            (pnode3, pnode4): 1,
            (pnode4, pnode5): 1,}
        return (length_by_edge, pnode1, pnode5)"""),
        ]
