"""Autonomy-state and goal models."""

from __future__ import annotations

from datetime import datetime
import enum

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base, TimestampMixin


class AutonomyMode(enum.StrEnum):
    MANUAL = "manual"
    REFLEX_ONLY = "reflex_only"
    ASSISTED = "assisted"


class GoalType(enum.StrEnum):
    ACCUMULATE_RESOURCE = "ACCUMULATE_RESOURCE"
    REACH_WEALTH = "REACH_WEALTH"
    BUILD_BUILDING = "BUILD_BUILDING"
    REACH_SKILL_LEVEL = "REACH_SKILL_LEVEL"
    REACH_REGION = "REACH_REGION"
    EARN_TRAIT = "EARN_TRAIT"
    CUSTOM = "CUSTOM"


class GoalStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class AutonomyState(Base, TimestampMixin):
    __tablename__ = "autonomy_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    autopilot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mode: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=AutonomyMode.MANUAL.value,
    )
    standing_orders: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    spending_limit_per_hour: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    spending_this_hour: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    hour_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reflex_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_standing_orders_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_digest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reflex_log: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    agent = relationship("Agent", back_populates="autonomy_state")


class AgentGoal(Base, TimestampMixin):
    __tablename__ = "agent_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    goal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=GoalStatus.ACTIVE.value,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    target: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    progress: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent = relationship("Agent", back_populates="goals")
