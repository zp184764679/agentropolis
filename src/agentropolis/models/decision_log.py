"""Decision Log model - records every significant agent action for replay and analysis.

Each entry captures the action, context snapshot at decision time, and is later
resolved with the actual outcome so the player can review what worked and what didn't.
"""

import enum
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base, TimestampMixin


class DecisionType(enum.StrEnum):
    TRADE = "TRADE"
    COMBAT = "COMBAT"
    PRODUCTION = "PRODUCTION"
    TRAVEL = "TRAVEL"
    DIPLOMACY = "DIPLOMACY"
    GUILD = "GUILD"
    TRANSPORT = "TRANSPORT"


class AgentDecisionLog(Base, TimestampMixin):
    __tablename__ = "agent_decision_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # What kind of decision
    decision_type: Mapped[DecisionType] = mapped_column(
        Enum(DecisionType), nullable=False, index=True
    )

    # Human-readable summary: "在铁矿谷以850买入50 ORE"
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # Snapshot of context at decision time
    # e.g. {"market_price": 820, "balance": 50000, "inventory": {"ORE": 100}}
    context_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Reference to the entity involved (order_id, contract_id, building_id, etc.)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Region where the decision was made
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"), nullable=True
    )

    # Copper amount involved in the decision (for ROI calculations)
    amount_copper: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # ─── Outcome fields (filled later by resolve step) ──────────────────────

    # When the outcome was evaluated
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Outcome summary: "ORE涨到1100，盈利+12500"
    outcome_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Profit/loss in copper (positive = profit)
    profit_copper: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Whether the decision was profitable
    is_profitable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Numeric score 0-100 for decision quality (optional, for advanced analytics)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    agent = relationship("Agent", back_populates="decision_logs")

    def __repr__(self) -> str:
        return f"<DecisionLog {self.decision_type.value} agent={self.agent_id} profitable={self.is_profitable}>"
