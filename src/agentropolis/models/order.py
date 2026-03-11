"""Order model - market orders owned by companies or agents."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class OrderType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, enum.Enum):
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"


class TimeInForce(str, enum.Enum):
    GTC = "GTC"
    IOC = "IOC"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), index=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), index=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id"), nullable=False, index=True
    )
    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(16, 4), nullable=False)
    remaining: Mapped[float] = mapped_column(Numeric(16, 4), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=OrderStatus.OPEN,
        nullable=False,
        index=True,
    )
    time_in_force: Mapped[TimeInForce] = mapped_column(
        Enum(TimeInForce, values_callable=lambda obj: [e.value for e in obj]),
        default=TimeInForce.GTC,
        nullable=False,
    )
    created_at_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    company = relationship("Company", back_populates="orders")
    agent = relationship("Agent", back_populates="orders")
    resource = relationship("Resource", back_populates="orders")

    def __repr__(self) -> str:
        return (
            f"<Order {self.id} {self.order_type.value} {self.resource_id} "
            f"@{self.price} tif={self.time_in_force.value} qty={self.remaining}/{self.quantity}>"
        )
