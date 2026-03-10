"""Persistent control-plane policy state for preview/runtime guardrails."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from agentropolis.models.base import Base, TimestampMixin


class PreviewControlPlaneState(Base, TimestampMixin):
    __tablename__ = "preview_control_plane_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    surface_enabled_override: Mapped[bool | None] = mapped_column(Boolean)
    writes_enabled_override: Mapped[bool | None] = mapped_column(Boolean)
    warfare_mutations_enabled_override: Mapped[bool | None] = mapped_column(Boolean)
    degraded_mode_override: Mapped[bool | None] = mapped_column(Boolean)
    last_hydrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PreviewAgentPolicy(Base, TimestampMixin):
    __tablename__ = "preview_agent_policies"

    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id"),
        primary_key=True,
    )
    allowed_families: Mapped[list[str] | None] = mapped_column(JSON)
    family_budgets: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_budget_refill_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ControlPlaneAuditLog(Base):
    __tablename__ = "control_plane_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    target_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), index=True)
    request_id: Mapped[str | None] = mapped_column(String(120), index=True)
    client_fingerprint: Mapped[str | None] = mapped_column(String(120))
    reason_code: Mapped[str | None] = mapped_column(String(64), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
