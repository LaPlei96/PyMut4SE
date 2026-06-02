from datasets.quixbugs.inputs.code.inputs import Inputs
from pymut4se.model.input import ProgramInput as Input
from datasets.quixbugs.src.node import Node

class InputsTopologicalOrdering(Inputs):
    def get_inputs():
        five = Node(5)
        seven = Node(7)
        three = Node(3)
        eleven = Node(11)
        eight = Node(8)
        two = Node(2)
        nine = Node(9)
        ten = Node(10)

        five.outgoing_nodes = [eleven]
        seven.outgoing_nodes = [eleven, eight]
        three.outgoing_nodes = [eight, ten]
        eleven.incoming_nodes = [five, seven]
        eleven.outgoing_nodes = [two, nine, ten]
        eight.incoming_nodes = [seven, three]
        eight.outgoing_nodes = [nine]
        two.incoming_nodes = [eleven]
        nine.incoming_nodes = [eleven, eight]
        ten.incoming_nodes = [eleven, three]

        pfive = Node(5)
        pzero = Node(0)
        pfour = Node(4)
        pone = Node(1)
        ptwo = Node(2)
        pthree = Node(3)

        pfive.outgoing_nodes = [ptwo, pzero]
        pfour.outgoing_nodes = [pzero, pone]
        ptwo.incoming_nodes = [pfive]
        ptwo.outgoing_nodes = [pthree]
        pzero.incoming_nodes = [pfive, pfour]
        pone.incoming_nodes = [pfour, pthree]
        pthree.incoming_nodes = [ptwo]
        pthree.outgoing_nodes = [pone]

        milk = Node("3/4 cup milk")
        egg = Node("1 egg")
        oil = Node("1 Tbl oil")
        mix = Node("1 cup mix")
        syrup = Node("heat syrup")
        griddle = Node("heat griddle")
        pour = Node("pour 1/4 cup")
        turn = Node("turn when bubbly")
        eat = Node("eat")

        milk.outgoing_nodes = [mix]
        egg.outgoing_nodes = [mix]
        oil.outgoing_nodes = [mix]
        mix.incoming_nodes = [milk, egg, oil]
        mix.outgoing_nodes = [syrup, pour]
        griddle.outgoing_nodes = [pour]
        pour.incoming_nodes = [mix, griddle]
        pour.outgoing_nodes = [turn]
        turn.incoming_nodes = [pour]
        turn.outgoing_nodes = [eat]
        syrup.incoming_nodes = [mix]
        syrup.outgoing_nodes = [eat]
        eat.incoming_nodes = [syrup, turn]

        return [
            Input.from_value(([five, seven, three, eleven, eight, two, nine, ten],), """        five = Node(5)
        seven = Node(7)
        three = Node(3)
        eleven = Node(11)
        eight = Node(8)
        two = Node(2)
        nine = Node(9)
        ten = Node(10)

        five.outgoing_nodes = [eleven]
        seven.outgoing_nodes = [eleven, eight]
        three.outgoing_nodes = [eight, ten]
        eleven.incoming_nodes = [five, seven]
        eleven.outgoing_nodes = [two, nine, ten]
        eight.incoming_nodes = [seven, three]
        eight.outgoing_nodes = [nine]
        two.incoming_nodes = [eleven]
        nine.incoming_nodes = [eleven, eight]
        ten.incoming_nodes = [eleven, three] return ([five, seven, three, eleven, eight, two, nine, ten],)"""),
            Input.from_value(([pzero, pone, ptwo, pthree, pfour, pfive],), """
        pfive = Node(5)
        pzero = Node(0)
        pfour = Node(4)
        pone = Node(1)
        ptwo = Node(2)
        pthree = Node(3)

        pfive.outgoing_nodes = [ptwo, pzero]
        pfour.outgoing_nodes = [pzero, pone]
        ptwo.incoming_nodes = [pfive]
        ptwo.outgoing_nodes = [pthree]
        pzero.incoming_nodes = [pfive, pfour]
        pone.incoming_nodes = [pfour, pthree]
        pthree.incoming_nodes = [ptwo]
        pthree.outgoing_nodes = [pone]
        return ([pzero, pone, ptwo, pthree, pfour, pfive],)"""),
            Input.from_value(([milk, egg, oil, mix, syrup, griddle, pour, turn, eat],), """        milk = Node("3/4 cup milk")
        egg = Node("1 egg")
        oil = Node("1 Tbl oil")
        mix = Node("1 cup mix")
        syrup = Node("heat syrup")
        griddle = Node("heat griddle")
        pour = Node("pour 1/4 cup")
        turn = Node("turn when bubbly")
        eat = Node("eat")

        milk.outgoing_nodes = [mix]
        egg.outgoing_nodes = [mix]
        oil.outgoing_nodes = [mix]
        mix.incoming_nodes = [milk, egg, oil]
        mix.outgoing_nodes = [syrup, pour]
        griddle.outgoing_nodes = [pour]
        pour.incoming_nodes = [mix, griddle]
        pour.outgoing_nodes = [turn]
        turn.incoming_nodes = [pour]
        turn.outgoing_nodes = [eat]
        syrup.incoming_nodes = [mix]
        syrup.outgoing_nodes = [eat]
        eat.incoming_nodes = [syrup, turn]

        return ([milk, egg, oil, mix, syrup, griddle, pour, turn, eat],)"""),
        ]
