"""BuildingType model - factory blueprints that can be constructed."""

from sqlalchemy import JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class BuildingType(Base):
    __tablename__ = "building_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    cost_credits: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    cost_materials: Mapped[dict] = mapped_column(JSON, default=dict)
    max_workers: Mapped[int] = mapped_column(default=10)
    description: Mapped[str] = mapped_column(Text, default="")

    # Relationships
    recipes = relationship("Recipe", back_populates="building_type")
    buildings = relationship("Building", back_populates="building_type")

    def __repr__(self) -> str:
        return f"<BuildingType {self.name}>"
