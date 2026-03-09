"""Notification model - event feed for agents."""

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class NotificationType(enum.StrEnum):
    ORDER_FILLED = "order_filled"
    TRANSPORT_ARRIVED = "transport_arrived"
    VITALS_LOW = "vitals_low"
    CONTRACT_OFFER = "contract_offer"
    ATTACK_INCOMING = "attack_incoming"
    BUILDING_DAMAGED = "building_damaged"
    WAGES_PAID = "wages_paid"
    BANKRUPTCY_WARNING = "bankruptcy_warning"
    EVENT_STARTED = "event_started"
    GENERAL = "general"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict | None] = mapped_column(JSON)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    agent = relationship("Agent")

    def __repr__(self) -> str:
        return f"<Notification {self.id} agent={self.agent_id} type={self.event_type}>"
