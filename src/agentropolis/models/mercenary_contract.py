"""MercenaryContract + ContractParticipant models - economic warfare system."""

import enum
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base, TimestampMixin


class MissionType(enum.StrEnum):
    SABOTAGE_BUILDING = "sabotage_building"
    RAID_TRANSPORT = "raid_transport"
    DEFEND_BUILDING = "defend_building"
    ESCORT_TRANSPORT = "escort_transport"


class ContractStatus(enum.StrEnum):
    OPEN = "open"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ParticipantRole(enum.StrEnum):
    ATTACKER = "attacker"
    DEFENDER = "defender"


class ParticipantStatus(enum.StrEnum):
    ENLISTED = "enlisted"
    ACTIVE = "active"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    FLED = "fled"


class MercenaryContract(Base, TimestampMixin):
    __tablename__ = "mercenary_contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    employer_agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id"), nullable=False, index=True
    )
    mission_type: Mapped[MissionType] = mapped_column(
        Enum(MissionType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    target_building_id: Mapped[int | None] = mapped_column(ForeignKey("buildings.id"))
    target_region_id: Mapped[int] = mapped_column(
        ForeignKey("regions.id"), nullable=False, index=True
    )
    target_transport_id: Mapped[int | None] = mapped_column(ForeignKey("transport_orders.id"))
    reward_per_agent: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_agents: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    escrow_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    mission_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ContractStatus.OPEN,
        nullable=False,
    )
    result_summary: Mapped[dict | None] = mapped_column(JSON)

    # Relationships
    employer = relationship("Agent", foreign_keys=[employer_agent_id])
    target_building = relationship("Building", foreign_keys=[target_building_id])
    target_region = relationship("Region", foreign_keys=[target_region_id])
    target_transport = relationship("TransportOrder", foreign_keys=[target_transport_id])
    participants = relationship("ContractParticipant", back_populates="contract", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<MercenaryContract {self.id} {self.mission_type} {self.status}>"


class ContractParticipant(Base, TimestampMixin):
    __tablename__ = "contract_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("mercenary_contracts.id"), nullable=False, index=True
    )
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id"), nullable=False, index=True
    )
    role: Mapped[ParticipantRole] = mapped_column(
        Enum(ParticipantRole, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    status: Mapped[ParticipantStatus] = mapped_column(
        Enum(ParticipantStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ParticipantStatus.ENLISTED,
        nullable=False,
    )
    reward_paid: Mapped[int] = mapped_column(BigInteger, default=0)
    health_lost: Mapped[float] = mapped_column(Float, default=0.0)
    xp_earned: Mapped[int] = mapped_column(Integer, default=0)
    combat_skill_name: Mapped[str | None] = mapped_column(String(50))

    # Relationships
    contract = relationship("MercenaryContract", back_populates="participants")
    agent = relationship("Agent", foreign_keys=[agent_id])

    def __repr__(self) -> str:
        return f"<ContractParticipant contract={self.contract_id} agent={self.agent_id} {self.role}>"
