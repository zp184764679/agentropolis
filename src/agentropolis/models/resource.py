"""Resource model - the 10 tradeable commodities."""

import enum

from sqlalchemy import Enum, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class ResourceCategory(str, enum.Enum):
    RAW = "raw"
    CONSUMABLE = "consumable"
    REFINED = "refined"
    COMPONENT = "component"


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[ResourceCategory] = mapped_column(
        Enum(ResourceCategory, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    base_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")

    # Relationships
    inventories = relationship("Inventory", back_populates="resource")
    orders = relationship("Order", back_populates="resource")
    price_history = relationship("PriceHistory", back_populates="resource")
    trades = relationship("Trade", back_populates="resource")

    def __repr__(self) -> str:
        return f"<Resource {self.ticker}>"
