"""Application configuration via environment variables.

This file still contains several legacy scaffold knobs (`*_PER_TICK`, company-economy defaults).
Treat it as transitional until the shared world kernel and control-plane settings are consolidated.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://agentropolis:agentropolis_dev@localhost:5432/agentropolis"

    # Legacy scaffold game mechanics
    TICK_INTERVAL_SECONDS: int = 60
    INITIAL_BALANCE: int = 10_000
    INITIAL_WORKERS: int = 100
    WORKER_RAT_PER_TICK: float = 0.5  # RAT consumed per worker per tick
    WORKER_DW_PER_TICK: float = 0.3  # DW consumed per worker per tick
    SATISFACTION_DECAY_RATE: float = 10.0  # % lost per tick when supplies missing
    SATISFACTION_RECOVERY_RATE: float = 5.0  # % recovered per tick when supplies available
    LOW_SATISFACTION_THRESHOLD: float = 50.0  # below this, production halved
    WORKER_ATTRITION_RATE: float = 0.05  # fraction of workers lost when satisfaction=0

    # Legacy scaffold rate limiting
    MAX_API_CALLS_PER_TICK: int = 100

    # API Key
    API_KEY_LENGTH: int = 32

    # Preview control-plane guard
    PREVIEW_SURFACE_ENABLED: bool = True
    PREVIEW_WRITES_ENABLED: bool = True
    WARFARE_MUTATIONS_ENABLED: bool = True
    PREVIEW_DEGRADED_MODE: bool = False
    PREVIEW_MUTATION_WINDOW_SECONDS: int = 60
    PREVIEW_AGENT_MUTATIONS_PER_WINDOW: int = 60
    PREVIEW_AGENT_SELF_MUTATIONS_PER_WINDOW: int = 30
    PREVIEW_WORLD_MUTATIONS_PER_WINDOW: int = 20
    PREVIEW_TRANSPORT_MUTATIONS_PER_WINDOW: int = 20
    PREVIEW_SOCIAL_MUTATIONS_PER_WINDOW: int = 20
    PREVIEW_STRATEGY_MUTATIONS_PER_WINDOW: int = 20
    PREVIEW_WARFARE_MUTATIONS_PER_WINDOW: int = 10
    PREVIEW_REGISTRATIONS_PER_WINDOW_PER_HOST: int = 10
    CONTROL_PLANE_ADMIN_TOKEN: str | None = None

    # Target world kernel defaults
    AGENT_BASE_CARRY_KG: int = 50
    AGENT_CARRY_PER_STRENGTH_LEVEL: int = 10
    AGENT_BASE_STORAGE_PER_REGION: int = 500
    AGENT_RESPAWN_PENALTY: float = 0.25
    AGENT_HUNGER_DECAY_PER_HOUR: float = 8.0
    AGENT_THIRST_DECAY_PER_HOUR: float = 12.0
    AGENT_ENERGY_DECAY_PER_HOUR: float = 6.0
    AGENT_HEALTH_DECAY_WHEN_STARVING_PER_HOUR: float = 10.0
    AGENT_HEALTH_DECAY_WHEN_DEHYDRATED_PER_HOUR: float = 14.0
    AGENT_EAT_HUNGER_RESTORE: float = 24.0
    AGENT_DRINK_THIRST_RESTORE: float = 30.0
    AGENT_REST_ENERGY_RESTORE: float = 35.0
    AGENT_REST_HAPPINESS_RESTORE: float = 4.0
    EMPLOYMENT_DEFAULT_SALARY_PER_SECOND: int = 1
    BUILDING_NATURAL_DECAY_PER_HOUR: float = 0.5

    # Guild progression costs
    GUILD_L2_COPPER_COST: int = 500_000
    GUILD_L2_NXC_COST: int = 10
    GUILD_L3_COPPER_COST: int = 2_000_000
    GUILD_L3_NXC_COST: int = 50
    GUILD_L4_COPPER_COST: int = 5_000_000
    GUILD_L4_NXC_COST: int = 100

    # Notifications and NPC shops
    NOTIFICATION_PRUNE_DAYS: int = 30
    NPC_SHOP_DEFAULT_ELASTICITY: float = 0.5
    NPC_SHOP_MIN_PRICE_MULTIPLIER: float = 0.5
    NPC_SHOP_MAX_PRICE_MULTIPLIER: float = 2.0

    # Regional projects
    PROJECT_ROAD_IMPROVEMENT_COST: int = 250_000
    PROJECT_MARKET_EXPANSION_COST: int = 400_000
    PROJECT_FORTIFICATION_COST: int = 650_000
    PROJECT_TRADE_HUB_COST: int = 1_000_000

    # Reputation tuning
    REPUTATION_TRADE_BONUS: float = 1.0
    REPUTATION_CONTRACT_BREACH_PENALTY: float = 10.0
    REPUTATION_SHOP_BAN_THRESHOLD: float = -50.0

    # Warfare tuning
    WARFARE_BASE_ATTACK_DAMAGE: float = 12.0
    WARFARE_BASE_COUNTER_DAMAGE: float = 9.0
    WARFARE_BASE_SABOTAGE_DAMAGE: float = 8.0
    WARFARE_CONTRACT_CANCEL_FEE_PCT: float = 0.1
    WARFARE_MAX_GARRISON_PER_BUILDING: int = 5
    WARFARE_NATURAL_REPAIR_PER_MINUTE: float = 0.25
    WARFARE_RAID_SUCCESS_THRESHOLD: float = 0.55
    WARFARE_REPAIR_BLD_PER_10_DURABILITY: int = 1


settings = Settings()
