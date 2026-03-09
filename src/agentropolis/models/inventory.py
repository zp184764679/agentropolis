"""Inventory model - resource stockpiles per company."""

from sqlalchemy import ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class Inventory(Base):
    __tablename__ = "inventories"
    __table_args__ = (UniqueConstraint("company_id", "resource_id", name="uq_company_resource"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id"), nullable=False, index=True
    )
    quantity: Mapped[float] = mapped_column(Numeric(16, 4), nullable=False, default=0)
    reserved: Mapped[float] = mapped_column(Numeric(16, 4), nullable=False, default=0)

    # Relationships
    company = relationship("Company", back_populates="inventories")
    resource = relationship("Resource", back_populates="inventories")

    @property
    def available(self) -> float:
        """Quantity available for sale or use (not reserved by open sell orders)."""
        return float(self.quantity) - float(self.reserved)

    def __repr__(self) -> str:
        return f"<Inventory company={self.company_id} resource={self.resource_id} qty={self.quantity}>"
