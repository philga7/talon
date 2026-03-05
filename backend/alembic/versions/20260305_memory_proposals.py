"""Add memory_proposals table for curated long-term facts.

Revision ID: 20260305_memory_proposals
Revises: 20260226_persona_id
Create Date: 2026-03-05
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260305_memory_proposals"
down_revision: Union[str, None] = "20260226_persona_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE memory_proposals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            persona_id VARCHAR(64) NOT NULL DEFAULT 'main',
            category VARCHAR(128) NOT NULL,
            key VARCHAR(256) NOT NULL,
            value TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 1,
            confidence DOUBLE PRECISION NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            source_session_id VARCHAR(128),
            source_entry_ids TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX ix_memory_proposals_persona ON memory_proposals (persona_id)")
    op.execute(
        "CREATE INDEX ix_memory_proposals_source_session "
        "ON memory_proposals (source_session_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memory_proposals_source_session")
    op.execute("DROP INDEX IF EXISTS ix_memory_proposals_persona")
    op.execute("DROP TABLE IF EXISTS memory_proposals")

