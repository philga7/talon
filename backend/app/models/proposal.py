"""Memory proposal model for curated long-term facts."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MemoryProposalStatus(StrEnum):
    """Lifecycle status for a memory proposal."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MemoryProposal(Base):
    """Structured candidate fact derived from episodic memory."""

    __tablename__ = "memory_proposals"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    persona_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        default="main",
    )
    category: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=MemoryProposalStatus.PENDING.value,
    )
    source_session_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    # JSON-encoded list of episodic entry IDs that informed this proposal.
    source_entry_ids: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

