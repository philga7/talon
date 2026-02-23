"""Initial migration (Phase 1 foundation).

Revision ID: 20260222_initial
Revises:
Create Date: 2026-02-22

This migration intentionally creates no tables. Schema objects are added in
subsequent revisions (for example, episodic_memory in Phase 3).
"""
from typing import Sequence, Union

revision: str = "20260222_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op upgrade for initial revision."""
    return None


def downgrade() -> None:
    """No-op downgrade for initial revision."""
    return None
