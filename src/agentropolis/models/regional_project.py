"""RegionalProject model - regional infrastructure development projects."""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class ProjectType(enum.StrEnum):
    ROAD_IMPROVEMENT = "road_improvement"
    MARKET_EXPANSION = "market_expansion"
    FORTIFICATION = "fortification"
    TRADE_HUB = "trade_hub"


class ProjectStatus(enum.StrEnum):
    FUNDING = "funding"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RegionalProject(Base):
    __tablename__ = "regional_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False, index=True)
    project_type: Mapped[ProjectType] = mapped_column(
        Enum(ProjectType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    copper_cost: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nxc_cost: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    copper_funded: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    nxc_funded: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    effect_value: Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ProjectStatus.FUNDING,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    initiated_by_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))

    # Relationships
    region = relationship("Region")
    initiator = relationship("Agent")

    def __repr__(self) -> str:
        return f"<RegionalProject {self.id} {self.project_type} region={self.region_id}>"
