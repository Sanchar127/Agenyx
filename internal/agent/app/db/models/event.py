from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ExecutionEventModel(Base):
    """Persistent append-only execution event."""

    __tablename__ = "execution_events"

    __table_args__ = (
        UniqueConstraint(
            "execution_id",
            "sequence",
            name="uq_execution_event_sequence",
        ),
    )

    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("executions.execution_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    execution: Mapped["ExecutionModel"] = relationship(
        "ExecutionModel",
        back_populates="events",
    )
