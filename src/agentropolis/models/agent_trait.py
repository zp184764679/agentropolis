"""Agent Trait model - earned traits based on behavior patterns.

Traits are automatically awarded based on accumulated actions and provide
small mechanical bonuses. They are publicly visible (intelligence system)
and decay over time if the agent stops being active in that area.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base, TimestampMixin


class TraitId(enum.StrEnum):
    IRON_TRADER = "IRON_TRADER"          # 100+ profitable trades → trade tax -5%
    WARMONGER = "WARMONGER"              # 20+ successful attacks → attack +10%
    IRON_WALL = "IRON_WALL"             # 15+ successful defenses → garrison defense +15%
    SUPPLY_MASTER = "SUPPLY_MASTER"      # 5+ profitable buildings → production speed +10%
    BACKSTABBER = "BACKSTABBER"          # 5+ broken treaties → trust -20%, raid loot +20%
    NXC_TYCOON = "NXC_TYCOON"          # 1000+ NXC held → mining output +5%
    PHOENIX = "PHOENIX"                  # 10+ respawns without bankruptcy → respawn balance +25%
    ROAD_WARRIOR = "ROAD_WARRIOR"        # 50+ region travels → travel time -10%
    GUILD_LEADER = "GUILD_LEADER"        # Lead guild with 10+ members → guild XP +10%
    MERCHANT_PRINCE = "MERCHANT_PRINCE"  # 1M+ copper in trades → NPC prices -5%


class TraitTier(int, enum.Enum):
    BRONZE = 1    # Base unlock
    SILVER = 2    # 2x requirement
    GOLD = 3      # 5x requirement


class AgentTrait(Base, TimestampMixin):
    __tablename__ = "agent_traits"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    trait_id: Mapped[TraitId] = mapped_column(
        Enum(TraitId), nullable=False
    )

    tier: Mapped[TraitTier] = mapped_column(
        Enum(TraitTier), nullable=False, default=TraitTier.BRONZE
    )

    # Progress toward next tier (or toward maintaining current tier)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Bonus multiplier (scales with tier: bronze=1.0, silver=1.5, gold=2.0)
    bonus_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # When the trait was first earned
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Last time progress was updated (for decay calculation)
    last_progress_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    agent = relationship("Agent", back_populates="traits")

    __table_args__ = (
        UniqueConstraint("agent_id", "trait_id", name="uq_agent_trait"),
    )

    def __repr__(self) -> str:
        return f"<AgentTrait {self.trait_id.value} tier={self.tier.name} agent={self.agent_id}>"
