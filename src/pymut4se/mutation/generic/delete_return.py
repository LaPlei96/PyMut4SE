import ast

from pymut4se.mutation.generic.delete import _DeleteStatementMutation


class DeleteReturnMutation(_DeleteStatementMutation):
    """Delete return statements and repair bodies that become empty."""

    statement_types = (ast.Return,)
    mutation_type = "delete_return"
