"""Building model - production facilities owned by companies."""

import enum

from sqlalchemy import Enum, ForeignKey, String
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
    building_type_id: Mapped[int] = mapped_column(
        ForeignKey("building_types.id"), nullable=False
    )
    active_recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"))
    production_progress: Mapped[int] = mapped_column(default=0)
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
