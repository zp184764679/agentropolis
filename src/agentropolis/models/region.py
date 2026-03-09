"""Region model - world geography with connections."""

import enum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentropolis.models.base import Base


class SafetyTier(enum.StrEnum):
    CORE = "core"
    BORDER = "border"
    RESOURCE = "resource"
    WILDERNESS = "wilderness"


class RegionType(enum.StrEnum):
    CAPITAL = "capital"
    TOWN = "town"
    VILLAGE = "village"
    OUTPOST = "outpost"
    WILDERNESS = "wilderness"


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    safety_tier: Mapped[SafetyTier]
    region_type: Mapped[RegionType]
    price_coefficient: Mapped[float] = mapped_column(Float, default=1.0)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.05)
    treasury: Mapped[int] = mapped_column(BigInteger, default=0)
    resource_specializations: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(Text, default="")

    # Relationships
    connections_from = relationship("RegionConnection", foreign_keys="RegionConnection.from_region_id", back_populates="from_region")
    connections_to = relationship("RegionConnection", foreign_keys="RegionConnection.to_region_id", back_populates="to_region")

    def __repr__(self) -> str:
        return f"<Region {self.name}>"


class RegionConnection(Base):
    __tablename__ = "region_connections"
    __table_args__ = (UniqueConstraint("from_region_id", "to_region_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    from_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    to_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    travel_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    terrain_type: Mapped[str] = mapped_column(String(30), default="road")
    is_portal: Mapped[bool] = mapped_column(Boolean, default=False)
    danger_level: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    from_region = relationship("Region", foreign_keys=[from_region_id], back_populates="connections_from")
    to_region = relationship("Region", foreign_keys=[to_region_id], back_populates="connections_to")

    def __repr__(self) -> str:
        return f"<RegionConnection {self.from_region_id} -> {self.to_region_id}>"
