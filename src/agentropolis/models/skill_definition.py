"""SkillDefinition model - skill catalog."""

import enum

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentropolis.models.base import Base


class SkillCategory(enum.StrEnum):
    GATHERING = "gathering"
    CRAFTING = "crafting"
    COMMERCE = "commerce"
    SOCIAL = "social"
    COMBAT = "combat"


class SkillDefinition(Base):
    __tablename__ = "skill_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    category: Mapped[SkillCategory]
    description: Mapped[str] = mapped_column(Text, default="")
    prerequisites: Mapped[dict] = mapped_column(JSON, default=dict)
    xp_per_level: Mapped[dict] = mapped_column(JSON, default=dict)

    def __repr__(self) -> str:
        return f"<SkillDefinition {self.name}>"
