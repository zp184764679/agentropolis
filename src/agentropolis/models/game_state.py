"""GameState model - singleton row tracking global game state."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from agentropolis.models.base import Base


class GameState(Base):
    __tablename__ = "game_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    current_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tick_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    is_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<GameState tick={self.current_tick} running={self.is_running}>"
