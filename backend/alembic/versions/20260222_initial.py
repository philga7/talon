"""Initial migration (Phase 1 foundation).

Revision ID: 20260222_initial
Revises:
Create Date: 2026-02-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260222_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No tables in Phase 1; episodic_memory added in Phase 3."""
    pass


def downgrade() -> None:
    """No tables to drop."""
    pass
