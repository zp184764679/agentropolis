"""Agent model - the player entity (auth entity with API key)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base, TimestampMixin


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    # Vitals (0-100 scale, float for smooth decay)
    health: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    hunger: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    thirst: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    energy: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    happiness: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    reputation: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Location
    current_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    home_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)

    # Economy
    personal_balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # Career
    career_path: Mapped[str | None] = mapped_column(String(50))

    # State
    is_alive: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_vitals_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    current_region = relationship("Region", foreign_keys=[current_region_id])
    home_region = relationship("Region", foreign_keys=[home_region_id])
    companies = relationship("Company", back_populates="founder")
    skills = relationship("AgentSkill", back_populates="agent")
    employments = relationship("AgentEmployment", back_populates="agent")
    inventories = relationship("Inventory", back_populates="agent")
    orders = relationship("Order", back_populates="agent")
    strategy_profile = relationship("StrategyProfile", back_populates="agent", uselist=False)
    decision_logs = relationship("AgentDecisionLog", back_populates="agent")
    traits = relationship("AgentTrait", back_populates="agent")
    autonomy_state = relationship("AutonomyState", back_populates="agent", uselist=False)
    goals = relationship("AgentGoal", back_populates="agent")

    def __repr__(self) -> str:
        return f"<Agent {self.name}>"
