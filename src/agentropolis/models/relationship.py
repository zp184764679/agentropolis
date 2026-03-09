"""AgentRelationship model - inter-agent relationships."""

import enum

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from agentropolis.models.base import Base


class RelationType(enum.StrEnum):
    ALLIED = "allied"
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"
    HOSTILE = "hostile"
    WAR = "war"


class AgentRelationship(Base):
    __tablename__ = "agent_relationships"
    __table_args__ = (UniqueConstraint("agent_id", "target_agent_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    target_agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    relation_type: Mapped[RelationType] = mapped_column(default=RelationType.NEUTRAL)
    trust_score: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<AgentRelationship {self.agent_id}->{self.target_agent_id} {self.relation_type}>"
