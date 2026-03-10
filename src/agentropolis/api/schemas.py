from __future__ import annotations

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
    founder_agent_id: int | None = None
    region_id: int | None = None
    balance: float
    net_worth: float
    is_active: bool
    worker_count: int
    worker_satisfaction: float
    building_count: int
    created_at: str


class WorkerInfo(BaseModel):
    company_id: int | None = None
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


class PreviewControlPlaneResponse(BaseModel):
    surface_enabled: bool
    writes_enabled: bool
    warfare_mutations_enabled: bool
    degraded_mode: bool
    mutation_window_seconds: int
    agent_mutations_per_window: int
    registrations_per_window_per_host: int
    family_limits: dict[str, int] = Field(default_factory=dict)
    dangerous_operations: list[str] = Field(default_factory=list)
    agent_policy_count: int = 0
    audit_log_size: int = 0
    policy_features: dict = Field(default_factory=dict)
    rate_limit_store: str
    persistent_policy_store: str | None = None
    error_codes: dict[str, str] = Field(default_factory=dict)
    admin_api: dict = Field(default_factory=dict)
    agent_policies: list["PreviewAgentPolicyResponse"] = Field(default_factory=list)
    recent_audit_entries: list["ControlPlaneAuditEntry"] = Field(default_factory=list)


class PreviewControlPlaneUpdateRequest(BaseModel):
    surface_enabled: bool | None = None
    writes_enabled: bool | None = None
    warfare_mutations_enabled: bool | None = None
    degraded_mode: bool | None = None
    reason_code: str | None = Field(default=None, min_length=2, max_length=64)
    note: str | None = Field(default=None, min_length=2, max_length=280)


class PreviewAgentPolicyRequest(BaseModel):
    allowed_families: list[str] | None = None
    family_budgets: dict[str, int] | None = None
    operation_budgets: dict[str, int] | None = None
    denied_operations: list[str] | None = None
    max_spend_per_operation: int | None = Field(default=None, ge=0)
    remaining_spend_budget: int | None = Field(default=None, ge=0)
    reason_code: str | None = Field(default=None, min_length=2, max_length=64)
    note: str | None = Field(default=None, min_length=2, max_length=280)


class PreviewAgentBudgetRefillRequest(BaseModel):
    increments: dict[str, int]
    operation_increments: dict[str, int] | None = None
    spending_credits: int | None = Field(default=None, ge=1)
    reason_code: str | None = Field(default=None, min_length=2, max_length=64)
    note: str | None = Field(default=None, min_length=2, max_length=280)


class ControlPlaneActionRequest(BaseModel):
    reason_code: str | None = Field(default=None, min_length=2, max_length=64)
    note: str | None = Field(default=None, min_length=2, max_length=280)


class PreviewAgentPolicyResponse(BaseModel):
    agent_id: int
    allowed_families: list[str] | None = None
    family_budgets: dict[str, int] = Field(default_factory=dict)
    operation_budgets: dict[str, int] = Field(default_factory=dict)
    denied_operations: list[str] | None = None
    max_spend_per_operation: int | None = None
    remaining_spend_budget: int | None = None
    last_budget_refill_at: str | None = None
    last_spending_refill_at: str | None = None
    updated_at: str


class PreviewAgentPolicyListResponse(BaseModel):
    policies: list[PreviewAgentPolicyResponse] = Field(default_factory=list)


class ControlPlaneAuditEntry(BaseModel):
    event_id: int
    action: str
    actor: str
    target_agent_id: int | None = None
    request_id: str | None = None
    client_fingerprint: str | None = None
    reason_code: str | None = None
    note: str | None = None
    payload: dict = Field(default_factory=dict)
    occurred_at: str


class ControlPlaneAuditResponse(BaseModel):
    entries: list[ControlPlaneAuditEntry] = Field(default_factory=list)


class ExecutionJobResponse(BaseModel):
    job_id: int
    job_type: str
    status: str
    trigger_kind: str
    dedupe_key: str | None = None
    payload: dict = Field(default_factory=dict)
    result_summary: dict | None = None
    attempt_history: list[dict] = Field(default_factory=list)
    attempts: int
    max_attempts: int
    available_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    last_error: str | None = None
    dead_letter_reason: str | None = None
    accepted_at: str | None = None
    updated_at: str | None = None


class ExecutionJobListResponse(BaseModel):
    jobs: list[ExecutionJobResponse] = Field(default_factory=list)


class ExecutionBackfillRequest(BaseModel):
    requested_tick: int = Field(..., ge=1)
    period_end: str | None = None
    reason_code: str | None = Field(default=None, min_length=2, max_length=64)
    note: str | None = Field(default=None, min_length=2, max_length=280)


class ExecutionRepairRequest(BaseModel):
    reason_code: str | None = Field(default=None, min_length=2, max_length=64)
    note: str | None = Field(default=None, min_length=2, max_length=280)


class ExecutionPhaseContractResponse(BaseModel):
    phase_results_logged: bool
    phase_max_attempts: int
    latest_sweep: dict | None = None


class ExecutionSnapshotResponse(BaseModel):
    job_states: list[str] = Field(default_factory=list)
    job_types: list[str] = Field(default_factory=list)
    counts: dict = Field(default_factory=dict)
    retry_policy: dict = Field(default_factory=dict)
    backfill_policy: dict = Field(default_factory=dict)
    housekeeping_phase_contract: ExecutionPhaseContractResponse
    recent_jobs: list[ExecutionJobResponse] = Field(default_factory=list)


# ─── Target World / Agent Surface ───────────────────────────────────────────


class AgentRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    home_region_id: int | None = None


class AgentRegisterResponse(BaseModel):
    agent_id: int
    name: str
    api_key: str
    home_region_id: int
    current_region_id: int
    balance: int
    message: str = "Agent registered. Save your API key - it cannot be retrieved later."


class AgentCompanyCreateRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=100)


class AgentCompanyCreateResponse(BaseModel):
    company_id: int
    company_name: str
    founder_agent_id: int
    region_id: int | None = None
    api_key: str = Field(..., description="Store this! It cannot be retrieved again.")
    initial_balance: float
    message: str = "Company registered. Save your API key - it cannot be retrieved later."


class AgentStatus(BaseModel):
    agent_id: int
    name: str
    health: float
    hunger: float
    thirst: float
    energy: float
    happiness: float
    reputation: float
    current_region_id: int
    home_region_id: int
    personal_balance: int
    is_alive: bool
    career_path: str | None = None


class TraitInfo(BaseModel):
    trait_id: str
    tier: str
    progress: int
    bonus_multiplier: float


class StrategyProfileResponse(BaseModel):
    agent_id: int
    combat_doctrine: str
    risk_tolerance: float
    primary_focus: str
    secondary_focus: str | None = None
    default_stance: str
    standing_orders: dict | None = None
    version: int


class StrategyPublicProfileResponse(BaseModel):
    agent_id: int
    combat_doctrine: str
    primary_focus: str
    secondary_focus: str | None = None
    default_stance: str
    standing_orders: dict | None = None
    version: int


class StrategyProfileUpdateRequest(BaseModel):
    combat_doctrine: str | None = None
    risk_tolerance: float | None = Field(default=None, ge=0.0, le=1.0)
    primary_focus: str | None = None
    secondary_focus: str | None = None
    default_stance: str | None = None


class StandingOrderBuyRule(BaseModel):
    resource: str
    below_price: float = Field(..., gt=0)
    max_qty: float = Field(..., gt=0)
    source: str | None = None


class StandingOrderSellRule(BaseModel):
    resource: str
    above_price: float = Field(..., gt=0)
    min_qty: float = Field(..., gt=0)


class AutonomyStandingOrders(BaseModel):
    buy_rules: list[StandingOrderBuyRule] = Field(default_factory=list)
    sell_rules: list[StandingOrderSellRule] = Field(default_factory=list)


class AutonomyConfigResponse(BaseModel):
    agent_id: int
    autopilot_enabled: bool
    mode: str
    spending_limit_per_hour: int
    spending_this_hour: int
    hour_window_started_at: str | None = None
    last_reflex_at: str | None = None
    last_standing_orders_at: str | None = None
    last_digest_at: str | None = None


class AutonomyConfigUpdateRequest(BaseModel):
    autopilot_enabled: bool | None = None
    mode: str | None = None
    spending_limit_per_hour: int | None = Field(default=None, ge=0)


class StandingOrdersUpdateRequest(BaseModel):
    standing_orders: AutonomyStandingOrders


class GoalResponse(BaseModel):
    goal_id: int
    goal_type: str
    status: str
    priority: int
    target: dict = Field(default_factory=dict)
    progress: dict = Field(default_factory=dict)
    notes: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class GoalCreateRequest(BaseModel):
    goal_type: str
    priority: int = Field(default=100, ge=0, le=1000)
    target: dict = Field(default_factory=dict)
    notes: str | None = None


class GoalUpdateRequest(BaseModel):
    status: str | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    target: dict | None = None
    progress: dict | None = None
    notes: str | None = None


class GoalListResponse(BaseModel):
    goals: list[GoalResponse] = Field(default_factory=list)


class DigestNotificationEntry(BaseModel):
    notification_id: int
    event_type: str
    title: str
    body: str = ""
    is_read: bool
    created_at: str


class DigestDecisionEntry(BaseModel):
    id: int
    decision_type: str
    summary: str
    created_at: str
    resolved_at: str | None = None
    outcome_summary: str | None = None


class DigestGoalEntry(BaseModel):
    goal_id: int
    goal_type: str
    status: str
    progress: dict = Field(default_factory=dict)
    completed_at: str | None = None


class MarketMoverEntry(BaseModel):
    ticker: str
    previous_close: float | None = None
    current_close: float | None = None
    delta_pct: float | None = None


class DigestResponse(BaseModel):
    agent_id: int
    generated_at: str
    since: str | None = None
    unread_count: int
    notifications: list[DigestNotificationEntry] = Field(default_factory=list)
    recent_decisions: list[DigestDecisionEntry] = Field(default_factory=list)
    goal_updates: list[DigestGoalEntry] = Field(default_factory=list)
    market_movers: list[MarketMoverEntry] = Field(default_factory=list)


class DigestAckResponse(BaseModel):
    agent_id: int
    acknowledged_at: str
    unread_count: int


class DashboardResponse(BaseModel):
    generated_at: str
    agent: AgentStatus
    company: CompanyStatus | None = None
    travel: TravelStatus | None = None
    autonomy: AutonomyConfigResponse
    goals: list[GoalResponse] = Field(default_factory=list)
    digest_unread_count: int = 0
    latest_digest_at: str | None = None
    decision_summary: DecisionAnalysisResponse | dict


class MarketIntelResponse(BaseModel):
    agent_id: int
    region_id: int
    ticker: str
    analysis: MarketAnalysis
    order_book: OrderBookResponse
    recent_trades: list[TradeRecord] = Field(default_factory=list)


class RouteIntelResponse(BaseModel):
    agent_id: int
    from_region_id: int
    to_region_id: int
    path: list[int] = Field(default_factory=list)
    total_time_seconds: int


class OpportunityEntry(BaseModel):
    category: str
    ticker: str | None = None
    region_id: int | None = None
    score: float = 0.0
    summary: str
    data: dict = Field(default_factory=dict)


class OpportunityResponse(BaseModel):
    agent_id: int
    opportunities: list[OpportunityEntry] = Field(default_factory=list)


class AgentPublicProfile(BaseModel):
    agent_id: int
    name: str
    reputation: float
    is_alive: bool
    current_region_id: int
    career_path: str | None = None
    strategy: StrategyPublicProfileResponse | None = None
    traits: list[TraitInfo | dict] = Field(default_factory=list)


class RegionConnectionInfo(BaseModel):
    to_region_id: int
    travel_time_seconds: int
    terrain_type: str
    is_portal: bool
    danger_level: int


class RegionInfo(BaseModel):
    region_id: int
    name: str
    safety_tier: str
    region_type: str
    price_coefficient: float
    tax_rate: float
    treasury: int
    resource_specializations: dict = Field(default_factory=dict)
    description: str = ""
    connections: list[RegionConnectionInfo] = Field(default_factory=list)


class TravelRequest(BaseModel):
    to_region_id: int


class TravelStatus(BaseModel):
    agent_id: int
    from_region_id: int
    to_region_id: int
    departed_at: str | None = None
    arrives_at: str | None = None
    cargo: dict = Field(default_factory=dict)
    in_transit: bool = True


class WorldMapResponse(BaseModel):
    regions: list[RegionInfo] = Field(default_factory=list)


class SkillInfo(BaseModel):
    skill_name: str
    category: str
    description: str = ""
    prerequisites: dict = Field(default_factory=dict)


class AgentSkillInfo(BaseModel):
    skill_name: str
    level: int
    xp: int
    last_practiced_at: str | None = None


class GuildCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    home_region_id: int


class GuildPromoteRequest(BaseModel):
    agent_id: int
    new_rank: str


class GuildDepositRequest(BaseModel):
    amount: int = Field(..., gt=0)


class GuildMemberInfo(BaseModel):
    agent_id: int
    rank: str
    share_percentage: float = 0.0
    joined_at: str | None = None


class GuildInfo(BaseModel):
    guild_id: int
    name: str
    level: int
    treasury: int = 0
    home_region_id: int
    is_active: bool = True
    member_count: int = 0
    members: list[GuildMemberInfo] = Field(default_factory=list)


class TreatyInfo(BaseModel):
    treaty_id: int
    treaty_type: str
    party_a_agent_id: int | None = None
    party_a_guild_id: int | None = None
    party_b_agent_id: int | None = None
    party_b_guild_id: int | None = None
    terms: dict = Field(default_factory=dict)
    is_active: bool = True
    expires_at: str | None = None


class TreatyProposeRequest(BaseModel):
    treaty_type: str
    target_agent_id: int | None = None
    target_guild_id: int | None = None
    terms: dict | None = None
    duration_hours: int | None = Field(default=24, ge=1)


class RelationshipInfo(BaseModel):
    agent_id: int
    target_agent_id: int
    relation_type: str
    trust_score: int


class RelationshipSetRequest(BaseModel):
    target_agent_id: int
    relation_type: str
    trust_delta: int = 0


class TransportRequest(BaseModel):
    from_region_id: int
    to_region_id: int
    items: dict[str, int] = Field(default_factory=dict)
    transport_type: str = "backpack"


class TransportStatusResponse(BaseModel):
    transport_id: int
    owner_agent_id: int | None = None
    owner_company_id: int | None = None
    from_region_id: int
    to_region_id: int
    status: str
    items: dict[str, int] = Field(default_factory=dict)
    cost: int | None = None
    departed_at: str | None = None
    arrives_at: str | None = None


class DecisionLogEntry(BaseModel):
    id: int
    decision_type: str
    summary: str
    context_snapshot: dict | None = None
    reference_type: str | None = None
    reference_id: int | None = None
    region_id: int | None = None
    amount_copper: int
    created_at: str
    resolved_at: str | None = None
    outcome_summary: str | None = None
    profit_copper: int | None = None
    is_profitable: bool | None = None
    quality_score: float | None = None


class DecisionLogResponse(BaseModel):
    entries: list[DecisionLogEntry] = Field(default_factory=list)


class DecisionTypeAnalysis(BaseModel):
    total_decisions: int
    wins: int
    losses: int
    win_rate: float
    avg_profit_copper: int
    total_profit_copper: int
    best_profit_copper: int
    worst_profit_copper: int
    avg_quality_score: float | None = None


class DecisionOverallSummary(BaseModel):
    total_decisions: int
    total_wins: int
    overall_win_rate: float
    total_profit_copper: int


class DecisionAnalysisResponse(BaseModel):
    agent_id: int
    overall: DecisionOverallSummary
    by_type: dict[str, DecisionTypeAnalysis] = Field(default_factory=dict)


class CombatModifierResponse(BaseModel):
    attack_mult: float
    defense_mult: float
    doctrine_attack: float
    doctrine_defense: float
    trait_attack_bonus: float
    trait_defense_bonus: float


class EconomyModifierResponse(BaseModel):
    trade_profit_mult: float
    damage_taken_mult: float
    npc_price_mult: float
    stance_raid_loot_mult: float
    stance_npc_discount: float


class ActiveModifiersResponse(BaseModel):
    combat: CombatModifierResponse
    economy: EconomyModifierResponse
    xp_multipliers: dict[str, float] = Field(default_factory=dict)


class TrainingDashboardResponse(BaseModel):
    agent_id: int
    agent_name: str
    profile: StrategyProfileResponse
    active_modifiers: ActiveModifiersResponse
    traits: list[TraitInfo | dict] = Field(default_factory=list)
    decision_summary: DecisionAnalysisResponse | dict


class StandingOrderEntry(BaseModel):
    agent_id: int
    agent_name: str
    current_region_id: int
    combat_doctrine: str
    standing_orders: dict | None = None


class StandingOrdersResponse(BaseModel):
    standing_orders: list[StandingOrderEntry] = Field(default_factory=list)


class AutonomyStandingOrdersResponse(BaseModel):
    agent_id: int
    standing_orders: AutonomyStandingOrders


class ContractCreateRequest(BaseModel):
    mission_type: str
    target_region_id: int
    reward_per_agent: int = Field(..., gt=0)
    max_agents: int = Field(..., gt=0)
    target_building_id: int | None = None
    target_transport_id: int | None = None
    mission_duration_seconds: int = 300
    expires_in_seconds: int = 3600


class ContractParticipantResponse(BaseModel):
    agent_id: int
    role: str
    status: str
    reward_paid: int = 0
    health_lost: float = 0.0
    xp_earned: int = 0


class ContractListItemResponse(BaseModel):
    contract_id: int
    employer_agent_id: int
    mission_type: str
    target_region_id: int
    reward_per_agent: int
    max_agents: int
    enlisted: int
    status: str
    expires_at: str | None = None


class ContractDetailResponse(BaseModel):
    contract_id: int
    employer_agent_id: int
    mission_type: str
    target_building_id: int | None = None
    target_region_id: int
    target_transport_id: int | None = None
    reward_per_agent: int
    max_agents: int
    escrow_total: int
    status: str
    expires_at: str | None = None
    activated_at: str | None = None
    completed_at: str | None = None
    result_summary: dict | None = None
    participants: list[ContractParticipantResponse] = Field(default_factory=list)


class ContractListResponse(BaseModel):
    contracts: list[ContractListItemResponse] = Field(default_factory=list)


class ContractExecutionResponse(BaseModel):
    contract_id: int | None = None
    mission_type: str | None = None
    success: bool | None = None
    result_summary: dict | None = None
    building_damage_applied: float | None = None
    building_new_durability: float | None = None
    building_disabled: bool | None = None
    loot_fraction: float | None = None
    looted_items: dict[str, int] | None = None
    details: dict | None = None


class GarrisonResponse(BaseModel):
    building_id: int
    agent_id: int
    garrison_count: int
    max_garrison: int


class RepairResponse(BaseModel):
    building_id: int
    old_durability: float
    new_durability: float
    bld_cost: int
    status: str


class RegionThreatContractResponse(BaseModel):
    contract_id: int
    mission_type: str
    target_building_id: int | None = None
    target_transport_id: int | None = None
    enlisted_count: int
    status: str


class RegionThreatResponse(BaseModel):
    region_id: int
    active_threats: int
    contracts: list[RegionThreatContractResponse] = Field(default_factory=list)


PreviewControlPlaneResponse.model_rebuild()
