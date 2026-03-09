"""Company model - company entities during the agent/company migration."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base, TimestampMixin


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    founder_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), index=True)
    balance: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False, default=10_000)
    net_worth: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False, default=10_000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bankruptcy_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    founder = relationship("Agent", back_populates="companies", foreign_keys=[founder_agent_id])
    buildings = relationship("Building", back_populates="company")
    inventories = relationship("Inventory", back_populates="company")
    orders = relationship("Order", back_populates="company")
    workers = relationship("Worker", back_populates="company", uselist=False)
    employments = relationship("AgentEmployment", back_populates="company")
    buy_trades = relationship(
        "Trade", back_populates="buyer", foreign_keys="Trade.buyer_id"
    )
    sell_trades = relationship(
        "Trade", back_populates="seller", foreign_keys="Trade.seller_id"
    )

    def __repr__(self) -> str:
        return f"<Company {self.name}>"
