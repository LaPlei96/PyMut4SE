import ast

from pymut4se.mutation.generic.delete import _DeleteStatementMutation


class DeleteWhileMutation(_DeleteStatementMutation):
    """Delete complete ``while`` statements, including their ``else`` branches."""

    statement_types = (ast.While,)
    mutation_type = "delete_while"
