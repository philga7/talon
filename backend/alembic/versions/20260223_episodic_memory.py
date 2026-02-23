"""Add episodic_memory table with pgvector.

Revision ID: 20260223_episodic
Revises: 20260222_initial
Create Date: 2026-02-23

"""
from typing import Sequence, Union

from alembic import op

revision: str = "20260223_episodic"
down_revision: Union[str, None] = "20260222_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE episodic_memory (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id VARCHAR(128) NOT NULL,
            role VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            embedding vector(1536),
            source VARCHAR(64) NOT NULL DEFAULT 'chat',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            archived_at TIMESTAMPTZ,
            deleted_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX episodic_session_idx ON episodic_memory (session_id, created_at DESC) "
        "WHERE deleted_at IS NULL AND archived_at IS NULL"
    )
    op.execute(
        "CREATE INDEX episodic_embedding_idx ON episodic_memory "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS episodic_embedding_idx")
    op.execute("DROP INDEX IF EXISTS episodic_session_idx")
    op.execute("DROP TABLE IF EXISTS episodic_memory")
    # Leave vector extension installed; other DBs may use it
