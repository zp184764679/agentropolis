"""Trade model - executed transactions from matched orders."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    buy_order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    sell_order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id"), nullable=False, index=True
    )
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(16, 4), nullable=False)
    tick_executed: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    buyer = relationship("Company", back_populates="buy_trades", foreign_keys=[buyer_id])
    seller = relationship("Company", back_populates="sell_trades", foreign_keys=[seller_id])
    resource = relationship("Resource", back_populates="trades")

    def __repr__(self) -> str:
        return f"<Trade {self.id} {self.resource_id} {self.quantity}@{self.price} tick={self.tick_executed}>"
