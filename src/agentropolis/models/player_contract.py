"""PlayerContract model - escrow-backed player-to-player contracts."""

import enum
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class ContractType(enum.StrEnum):
    SUPPLY = "supply"
    PURCHASE = "purchase"
    TRANSPORT = "transport"
    CUSTOM = "custom"


class PlayerContractStatus(enum.StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    FULFILLED = "fulfilled"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class PlayerContract(Base):
    __tablename__ = "player_contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_type: Mapped[ContractType] = mapped_column(
        Enum(ContractType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    proposer_agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id"), nullable=False, index=True
    )
    acceptor_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id"), index=True
    )
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    terms: Mapped[dict] = mapped_column(JSON, nullable=False)
    escrow_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reward_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[PlayerContractStatus] = mapped_column(
        Enum(PlayerContractStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=PlayerContractStatus.PROPOSED,
        nullable=False,
        index=True,
    )
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    proposer = relationship("Agent", foreign_keys=[proposer_agent_id])
    acceptor = relationship("Agent", foreign_keys=[acceptor_agent_id])
    region = relationship("Region")

    def __repr__(self) -> str:
        return f"<PlayerContract {self.id} {self.contract_type} status={self.status}>"
