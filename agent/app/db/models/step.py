from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StepModel(Base):
    """
    PostgreSQL model representing a single execution step.
    """

    __tablename__ = "execution_steps"

    __table_args__ = (
        UniqueConstraint(
            "execution_id",
            "number",
            name="uq_execution_step_number",
        ),
    )

    step_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )

    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "executions.execution_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    input: Mapped[Any | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    output: Mapped[Any | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    execution: Mapped["ExecutionModel"] = relationship(
        "ExecutionModel",
        back_populates="steps",
    )
