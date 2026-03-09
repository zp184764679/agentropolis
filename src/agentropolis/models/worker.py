"""Worker model - labor force for each company."""

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), unique=True, nullable=False
    )
    count: Mapped[int] = mapped_column(nullable=False, default=100)
    satisfaction: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=100.0
    )

    # Relationships
    company = relationship("Company", back_populates="workers")

    def __repr__(self) -> str:
        return f"<Worker company={self.company_id} count={self.count} sat={self.satisfaction}%>"
