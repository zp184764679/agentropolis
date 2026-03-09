"""PriceHistory model - OHLCV candlestick data per resource per tick."""

from sqlalchemy import ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("resource_id", "tick", name="uq_resource_tick"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id"), nullable=False, index=True
    )
    tick: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    open: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(16, 4), nullable=False, default=0)

    # Relationships
    resource = relationship("Resource", back_populates="price_history")

    def __repr__(self) -> str:
        return f"<PriceHistory {self.resource_id} tick={self.tick} C={self.close}>"
