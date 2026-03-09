"""Guild model - player guilds with members and treasury."""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base, TimestampMixin


class GuildRank(enum.StrEnum):
    RECRUIT = "recruit"
    MEMBER = "member"
    OFFICER = "officer"
    LEADER = "leader"


class Guild(Base, TimestampMixin):
    __tablename__ = "guilds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1)
    treasury: Mapped[int] = mapped_column(BigInteger, default=0)
    home_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    maintenance_cost_per_day: Mapped[int] = mapped_column(BigInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    members = relationship("GuildMember", back_populates="guild")

    def __repr__(self) -> str:
        return f"<Guild {self.name}>"


class GuildMember(Base):
    __tablename__ = "guild_members"
    __table_args__ = (UniqueConstraint("guild_id", "agent_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id"), nullable=False, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    rank: Mapped[GuildRank]
    share_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    guild = relationship("Guild", back_populates="members")
    agent = relationship("Agent")

    def __repr__(self) -> str:
        return f"<GuildMember guild={self.guild_id} agent={self.agent_id}>"
