"""Inventory model - regional stockpiles owned by companies or agents."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class Inventory(Base):
    __tablename__ = "inventories"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "agent_id",
            "region_id",
            "resource_id",
            name="uq_inventory_owner_region_resource",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), index=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), index=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id"), nullable=False, index=True
    )
    quantity: Mapped[float] = mapped_column(Numeric(16, 4), nullable=False, default=0)
    reserved: Mapped[float] = mapped_column(Numeric(16, 4), nullable=False, default=0)
    last_decay_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    company = relationship("Company", back_populates="inventories")
    agent = relationship("Agent", back_populates="inventories")
    resource = relationship("Resource", back_populates="inventories")

    @property
    def available(self) -> float:
        """Quantity available for sale or use (not reserved by open sell orders)."""
        return float(self.quantity) - float(self.reserved)

    def __repr__(self) -> str:
        owner = f"company={self.company_id}" if self.company_id else f"agent={self.agent_id}"
        return f"<Inventory {owner} region={self.region_id} resource={self.resource_id} qty={self.quantity}>"
