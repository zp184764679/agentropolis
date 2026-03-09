"""Treaty model - formal agreements between agents/guilds."""

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from agentropolis.models.base import Base, TimestampMixin


class TreatyType(enum.StrEnum):
    NON_AGGRESSION = "non_aggression"
    MUTUAL_DEFENSE = "mutual_defense"
    TRADE_AGREEMENT = "trade_agreement"
    ALLIANCE = "alliance"


class Treaty(Base, TimestampMixin):
    __tablename__ = "treaties"

    id: Mapped[int] = mapped_column(primary_key=True)
    party_a_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    party_a_guild_id: Mapped[int | None] = mapped_column(ForeignKey("guilds.id"))
    party_b_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    party_b_guild_id: Mapped[int | None] = mapped_column(ForeignKey("guilds.id"))
    treaty_type: Mapped[TreatyType]
    terms: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Treaty {self.id} {self.treaty_type}>"
