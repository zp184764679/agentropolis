"""TaxRecord model - track tax collection per region."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from agentropolis.models.base import Base


class TaxRecord(Base):
    __tablename__ = "tax_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    tax_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payer_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    payer_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    beneficiary_guild_id: Mapped[int | None] = mapped_column(ForeignKey("guilds.id"))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<TaxRecord {self.id} {self.tax_type} amount={self.amount}>"
