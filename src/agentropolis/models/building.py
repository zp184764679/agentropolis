"""Building model - production facilities owned by companies inside regions."""

import enum

from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base, TimestampMixin


class BuildingStatus(str, enum.Enum):
    IDLE = "idle"
    PRODUCING = "producing"
    DISABLED = "disabled"


class Building(Base, TimestampMixin):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), index=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), index=True)
    building_type_id: Mapped[int] = mapped_column(
        ForeignKey("building_types.id"), nullable=False
    )
    active_recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"))
    production_progress: Mapped[int] = mapped_column(default=0)
    last_production_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    durability: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    max_durability: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    last_durability_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[BuildingStatus] = mapped_column(
        Enum(BuildingStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=BuildingStatus.IDLE,
        nullable=False,
    )

    # Relationships
    company = relationship("Company", back_populates="buildings")
    building_type = relationship("BuildingType", back_populates="buildings")
    active_recipe = relationship("Recipe", back_populates="buildings")

    def __repr__(self) -> str:
        return f"<Building {self.id} type={self.building_type_id} status={self.status}>"
