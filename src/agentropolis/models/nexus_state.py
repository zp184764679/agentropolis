"""NexusCrystalState model - singleton tracking global NXC mining state."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from agentropolis.models.base import Base


class NexusCrystalState(Base):
    __tablename__ = "nexus_crystal_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    # Mining totals
    total_mined: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    hard_cap: Mapped[int] = mapped_column(BigInteger, nullable=False, default=21_000_000)
    current_base_yield: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    # Difficulty adjustment
    current_difficulty: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    active_refineries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_emission_per_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    difficulty_adjusted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Halving
    halvings_applied: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cycles_since_genesis: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cycles_per_halving: Mapped[int] = mapped_column(Integer, nullable=False, default=2016)
    last_halving_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return (
            f"<NexusCrystalState mined={self.total_mined}/{self.hard_cap} "
            f"yield={self.current_base_yield} diff={self.current_difficulty}>"
        )
