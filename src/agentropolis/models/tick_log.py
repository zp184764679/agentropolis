"""TickLog model - per-tick execution summary."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from agentropolis.models.base import Base


class TickLog(Base):
    __tablename__ = "tick_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tick_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumption_summary: Mapped[dict | None] = mapped_column(JSON)
    production_summary: Mapped[dict | None] = mapped_column(JSON)
    trade_summary: Mapped[dict | None] = mapped_column(JSON)
    active_companies: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<TickLog tick={self.tick_number}>"
