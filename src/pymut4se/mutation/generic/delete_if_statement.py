import ast

from pymut4se.mutation.generic.delete import _DeleteStatementMutation


class DeleteIfStatementMutation(_DeleteStatementMutation):
    """Delete complete ``if`` statements, including their alternative branches."""

    statement_types = (ast.If,)
    mutation_type = "delete_if_statement"
