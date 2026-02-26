"""Add persona_id column to episodic_memory.

Revision ID: 20260226_persona_id
Revises: 20260223_episodic
Create Date: 2026-02-26
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260226_persona_id"
down_revision: Union[str, None] = "20260223_episodic"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE episodic_memory "
        "ADD COLUMN persona_id VARCHAR(64) NOT NULL DEFAULT 'main'"
    )
    op.execute("CREATE INDEX ix_episodic_persona ON episodic_memory (persona_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_episodic_persona")
    op.execute("ALTER TABLE episodic_memory DROP COLUMN IF EXISTS persona_id")
