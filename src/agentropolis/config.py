"""Application configuration via environment variables."""

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

    # Game mechanics
    TICK_INTERVAL_SECONDS: int = 60
    INITIAL_BALANCE: int = 10_000
    INITIAL_WORKERS: int = 100
    WORKER_RAT_PER_TICK: float = 0.5  # RAT consumed per worker per tick
    WORKER_DW_PER_TICK: float = 0.3  # DW consumed per worker per tick
    SATISFACTION_DECAY_RATE: float = 10.0  # % lost per tick when supplies missing
    SATISFACTION_RECOVERY_RATE: float = 5.0  # % recovered per tick when supplies available
    LOW_SATISFACTION_THRESHOLD: float = 50.0  # below this, production halved
    WORKER_ATTRITION_RATE: float = 0.05  # fraction of workers lost when satisfaction=0

    # Rate limiting
    MAX_API_CALLS_PER_TICK: int = 100

    # API Key
    API_KEY_LENGTH: int = 32


settings = Settings()
