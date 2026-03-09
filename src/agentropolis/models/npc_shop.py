"""NpcShop model - NPC vendors per region."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from agentropolis.models.base import Base


class NpcShop(Base):
    __tablename__ = "npc_shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False, index=True)
    shop_type: Mapped[str] = mapped_column(String(50), nullable=False)
    buy_prices: Mapped[dict] = mapped_column(JSON, default=dict)
    sell_prices: Mapped[dict] = mapped_column(JSON, default=dict)
    stock: Mapped[dict] = mapped_column(JSON, default=dict)
    restock_rate: Mapped[dict] = mapped_column(JSON, default=dict)
    max_stock: Mapped[dict] = mapped_column(JSON, default=dict)
    elasticity: Mapped[float] = mapped_column(Float, default=0.5)
    last_restock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<NpcShop {self.id} region={self.region_id} type={self.shop_type}>"
