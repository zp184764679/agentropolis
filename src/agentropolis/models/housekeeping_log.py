"""HousekeepingLog model - periodic sweep execution summary."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from agentropolis.models.base import Base


class HousekeepingLog(Base):
    __tablename__ = "housekeeping_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sweep_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    # Phase summaries (JSON blobs)
    consumption_summary: Mapped[dict | None] = mapped_column(JSON)
    production_summary: Mapped[dict | None] = mapped_column(JSON)
    trade_summary: Mapped[dict | None] = mapped_column(JSON)
    vitals_summary: Mapped[dict | None] = mapped_column(JSON)
    logistics_summary: Mapped[dict | None] = mapped_column(JSON)
    autonomy_summary: Mapped[dict | None] = mapped_column(JSON)
    digest_summary: Mapped[dict | None] = mapped_column(JSON)
    analytics_summary: Mapped[dict | None] = mapped_column(JSON)
    admin_summary: Mapped[dict | None] = mapped_column(JSON)
    nxc_summary: Mapped[dict | None] = mapped_column(JSON)

    # Per-phase wall-clock timings (seconds) for bottleneck diagnosis
    phase_timings: Mapped[dict | None] = mapped_column(JSON)

    # Stats
    active_companies: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list | None] = mapped_column(JSON)

    def __repr__(self) -> str:
        return f"<HousekeepingLog #{self.sweep_count} {self.period_start} duration={self.duration_seconds:.1f}s>"
