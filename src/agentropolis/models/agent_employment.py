"""AgentEmployment model - agent employment in companies."""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class EmploymentRole(enum.StrEnum):
    WORKER = "worker"
    FOREMAN = "foreman"
    MANAGER = "manager"
    DIRECTOR = "director"
    CEO = "ceo"


class AgentEmployment(Base):
    __tablename__ = "agent_employments"
    __table_args__ = (UniqueConstraint("agent_id", "company_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    role: Mapped[EmploymentRole]
    salary_per_second: Mapped[int] = mapped_column(BigInteger, default=0)
    hired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_wage_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    agent = relationship("Agent", back_populates="employments")
    company = relationship("Company", back_populates="employments")

    def __repr__(self) -> str:
        return f"<AgentEmployment agent={self.agent_id} company={self.company_id} role={self.role}>"
