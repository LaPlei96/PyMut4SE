from datasets.quixbugs.inputs.code.inputs import Inputs
from datasets.quixbugs.src.node import Node
from pymut4se.model.input import ProgramInput as Input

class InputsReverseLinkedList(Inputs):
    def get_inputs():
        node = Node(0)
        node1 = Node(1)
        node2 = Node(2, node1)
        node3 = Node(3, node2)
        node4 = Node(4, node3)
        node5 = Node(5, node4)
        return [
            Input.from_value((node5,), """node = Node(0)
        node1 = Node(1)
        node2 = Node(2, node1)
        node3 = Node(3, node2)
        node4 = Node(4, node3)
        node5 = Node(5, node4)
        return (node5,)"""),
            Input.from_value((node,), """node = Node(0)
        return (node,)"""),
            Input.from_value((None,), """
        (None,)"""),
        ]
