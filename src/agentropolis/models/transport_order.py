"""TransportOrder model - inter-region logistics."""

import enum
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from agentropolis.models.base import Base, TimestampMixin


class TransportStatus(enum.StrEnum):
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    LOST = "lost"


class TransportOrder(Base, TimestampMixin):
    __tablename__ = "transport_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    owner_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    from_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    to_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    items: Mapped[dict] = mapped_column(JSON, default=dict)
    total_weight: Mapped[int] = mapped_column(Integer, default=0)
    transport_type: Mapped[str] = mapped_column(String(30), default="backpack")
    cost: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[TransportStatus]
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrives_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<TransportOrder {self.id} {self.status}>"
