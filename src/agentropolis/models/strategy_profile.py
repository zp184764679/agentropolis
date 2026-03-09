"""Strategy Profile model - configurable combat doctrine and behavior parameters.

Players configure their Agent's strategy profile to produce real mechanical differences.
Two Agents with the same stats but different doctrines fight differently.
"""

import enum

from sqlalchemy import JSON, Enum, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base, TimestampMixin


class CombatDoctrine(enum.StrEnum):
    OFFENSIVE = "OFFENSIVE"      # +20% attack, -15% defense
    BALANCED = "BALANCED"        # no modifier
    DEFENSIVE = "DEFENSIVE"      # +25% defense, -10% attack
    PACIFIST = "PACIFIST"        # -50% combat, +10% commercial XP


class DiplomaticStance(enum.StrEnum):
    OPEN = "OPEN"                # +10 initial trust
    CAUTIOUS = "CAUTIOUS"        # 0 initial trust (default)
    HOSTILE = "HOSTILE"          # -15 initial trust, +5% raid loot
    ISOLATIONIST = "ISOLATIONIST"  # -5 initial trust, +5% NPC shop discount


class PrimaryFocus(enum.StrEnum):
    COMBAT = "COMBAT"            # Melee, Tactics, Fortification
    CRAFTING = "CRAFTING"        # Smithing, Engineering, Alchemy
    COMMERCE = "COMMERCE"        # Trading, Logistics, Negotiation
    GATHERING = "GATHERING"      # Mining, Woodcutting, Farming
    LEADERSHIP = "LEADERSHIP"    # Command, Diplomacy, Management


class StrategyProfile(Base, TimestampMixin):
    __tablename__ = "strategy_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    # Combat doctrine - affects attack/defense multipliers
    combat_doctrine: Mapped[CombatDoctrine] = mapped_column(
        Enum(CombatDoctrine), nullable=False, default=CombatDoctrine.BALANCED
    )

    # Risk tolerance 0.0 (conservative) to 1.0 (aggressive)
    # High: +15% trade profit, +20% combat damage taken
    # Low: NPC shop -10% discount, -10% trade profit
    risk_tolerance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    # Skill focus - determines XP gain rate modifiers
    primary_focus: Mapped[PrimaryFocus] = mapped_column(
        Enum(PrimaryFocus), nullable=False, default=PrimaryFocus.COMMERCE
    )
    secondary_focus: Mapped[PrimaryFocus | None] = mapped_column(
        Enum(PrimaryFocus), nullable=True
    )

    # Diplomatic default stance toward new agents
    default_stance: Mapped[DiplomaticStance] = mapped_column(
        Enum(DiplomaticStance), nullable=False, default=DiplomaticStance.CAUTIOUS
    )

    # Standing orders - public JSON (can be queried by other players)
    # e.g. {"buy_if": {"ORE": {"below": 700}}, "sell_if": {"ORE": {"above": 1200}}}
    standing_orders: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Profile version (incremented on each update for change tracking)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Relationships
    agent = relationship("Agent", back_populates="strategy_profile", uselist=False)

    def __repr__(self) -> str:
        return f"<StrategyProfile agent_id={self.agent_id} doctrine={self.combat_doctrine.value}>"
