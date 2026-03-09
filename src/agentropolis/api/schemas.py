"""Pydantic schemas for request/response validation.

This module defines the API contract. All REST endpoints and MCP tools
must use these schemas. Do NOT create ad-hoc dicts in route handlers.
"""

from pydantic import BaseModel, Field


# ─── Auth ────────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=100)


class RegisterResponse(BaseModel):
    company_id: int
    company_name: str
    api_key: str = Field(..., description="Store this! It cannot be retrieved again.")
    initial_balance: float
    message: str = "Company registered. Save your API key - it cannot be retrieved later."


# ─── Resource ────────────────────────────────────────────────────────────────


class ResourceInfo(BaseModel):
    ticker: str
    name: str
    category: str
    base_price: float
    description: str


# ─── Market ──────────────────────────────────────────────────────────────────


class MarketPrice(BaseModel):
    ticker: str
    name: str
    last_price: float | None
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    volume_24h: float


class OrderBookEntry(BaseModel):
    price: float
    quantity: float
    order_count: int


class OrderBookResponse(BaseModel):
    ticker: str
    bids: list[OrderBookEntry]
    asks: list[OrderBookEntry]


class PriceCandle(BaseModel):
    tick: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class PlaceOrderRequest(BaseModel):
    resource: str = Field(..., description="Resource ticker, e.g. 'H2O'")
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)


class OrderResponse(BaseModel):
    order_id: int
    order_type: str
    resource: str
    price: float
    quantity: float
    remaining: float
    status: str
    created_at_tick: int


class CancelOrderRequest(BaseModel):
    order_id: int


class TradeRecord(BaseModel):
    trade_id: int
    buyer: str
    seller: str
    resource: str
    price: float
    quantity: float
    tick: int


class MarketAnalysis(BaseModel):
    ticker: str
    avg_price_10t: float | None
    price_trend: str  # "rising", "falling", "stable"
    supply_demand_ratio: float | None
    total_buy_volume: float
    total_sell_volume: float
    trade_count_10t: int


# ─── Production ──────────────────────────────────────────────────────────────


class RecipeInfo(BaseModel):
    recipe_id: int
    name: str
    building_type: str
    inputs: dict[str, float]
    outputs: dict[str, float]
    duration_ticks: int


class BuildingInfo(BaseModel):
    building_id: int
    building_type: str
    status: str
    active_recipe: str | None
    production_progress: int
    recipe_duration: int | None


class StartProductionRequest(BaseModel):
    building_id: int
    recipe_id: int


class BuildBuildingRequest(BaseModel):
    building_type: str


class BuildingTypeInfo(BaseModel):
    name: str
    display_name: str
    cost_credits: float
    cost_materials: dict[str, float]
    max_workers: int
    description: str


# ─── Inventory ───────────────────────────────────────────────────────────────


class InventoryItem(BaseModel):
    ticker: str
    name: str
    quantity: float
    reserved: float
    available: float


class InventoryResponse(BaseModel):
    items: list[InventoryItem]
    total_value: float  # estimated based on last market prices


# ─── Company ─────────────────────────────────────────────────────────────────


class CompanyStatus(BaseModel):
    company_id: int
    name: str
    balance: float
    net_worth: float
    is_active: bool
    worker_count: int
    worker_satisfaction: float
    building_count: int
    created_at: str


class WorkerInfo(BaseModel):
    count: int
    satisfaction: float
    rat_consumption_per_tick: float
    dw_consumption_per_tick: float
    productivity_modifier: float  # 1.0 normal, 0.5 if low satisfaction


# ─── Game ────────────────────────────────────────────────────────────────────


class GameStatus(BaseModel):
    current_tick: int
    tick_interval_seconds: int
    is_running: bool
    next_tick_in_seconds: float | None
    total_companies: int
    active_companies: int


class LeaderboardEntry(BaseModel):
    rank: int
    company_name: str
    net_worth: float
    balance: float
    worker_count: int
    building_count: int


class LeaderboardResponse(BaseModel):
    metric: str
    entries: list[LeaderboardEntry]
    your_rank: int | None = None


# ─── Generic ─────────────────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


class SuccessResponse(BaseModel):
    message: str
