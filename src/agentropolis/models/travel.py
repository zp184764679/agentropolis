"""TravelQueue model - agent travel between regions."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class TravelQueue(Base):
    __tablename__ = "travel_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), unique=True, nullable=False)
    from_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    to_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    departed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arrives_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cargo: Mapped[dict] = mapped_column(JSON, default=dict)

    # Relationships
    agent = relationship("Agent")

    def __repr__(self) -> str:
        return f"<TravelQueue agent={self.agent_id} {self.from_region_id}->{self.to_region_id}>"
