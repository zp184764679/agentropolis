"""Execution job model for asynchronous maintenance and repair work."""

from __future__ import annotations

from datetime import datetime
import enum

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentropolis.models.base import Base, TimestampMixin


class ExecutionJobType(enum.StrEnum):
    HOUSEKEEPING_BACKFILL = "housekeeping_backfill"
    DERIVED_STATE_REPAIR = "derived_state_repair"


class ExecutionJobStatus(enum.StrEnum):
    ACCEPTED = "accepted"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class ExecutionTriggerKind(enum.StrEnum):
    MANUAL = "manual"
    BACKFILL = "backfill"
    RETRY = "retry"
    SCHEDULED = "scheduled"


class ExecutionJob(Base, TimestampMixin):
    __tablename__ = "execution_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ExecutionJobStatus.ACCEPTED.value,
        index=True,
    )
    trigger_kind: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ExecutionTriggerKind.MANUAL.value,
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(160), index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_summary: Mapped[dict | None] = mapped_column(JSON)
    attempt_history: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    dead_letter_reason: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<ExecutionJob #{self.id} {self.job_type} status={self.status}>"
