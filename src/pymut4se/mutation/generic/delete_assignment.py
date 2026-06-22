import ast

from pymut4se.mutation.generic.delete import _DeleteStatementMutation


class DeleteAssignmentMutation(_DeleteStatementMutation):
    """Delete regular, annotated, and augmented assignment statements."""

    statement_types = (ast.Assign, ast.AnnAssign, ast.AugAssign)
    mutation_type = "delete_assignment"
