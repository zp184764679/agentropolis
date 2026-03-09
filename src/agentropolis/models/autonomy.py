"""Minimal autonomy-state models for mapper completeness during migration."""

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base, TimestampMixin


class AutonomyState(Base, TimestampMixin):
    __tablename__ = "autonomy_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), unique=True, nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    state: Mapped[dict | None] = mapped_column(JSON)

    agent = relationship("Agent", back_populates="autonomy_state")


class AgentGoal(Base, TimestampMixin):
    __tablename__ = "agent_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    goal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    payload: Mapped[dict | None] = mapped_column(JSON)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    agent = relationship("Agent", back_populates="goals")
