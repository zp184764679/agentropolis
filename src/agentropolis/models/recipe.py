"""Recipe model - production formulas that transform inputs to outputs."""

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    building_type_id: Mapped[int] = mapped_column(ForeignKey("building_types.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    outputs: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ticks: Mapped[int] = mapped_column(nullable=False, default=1)
    description: Mapped[str] = mapped_column(Text, default="")

    # Relationships
    building_type = relationship("BuildingType", back_populates="recipes")
    buildings = relationship("Building", back_populates="active_recipe")

    def __repr__(self) -> str:
        return f"<Recipe {self.name}>"
