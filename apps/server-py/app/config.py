from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://musegraph:musegraph123@localhost:5432/musegraph"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    TASK_STATE_SQLITE_PATH: str = ".musegraph/task_state.sqlite3"

    # Session
    SESSION_EXPIRES_HOURS: int = 168  # 7 days

    # File storage (local persistent path)
    FILE_STORAGE_ROOT: str = ".musegraph/storage"

    # Cognee backend (project memory + vector + graph)
    COGNEE_DATA_DIR: str = ".musegraph/cognee"
    COGNEE_INGEST_TIMEOUT_SECONDS: int = 300
    COGNEE_LLM_MAX_TOKENS: int = 8192

    # Agent
    AGENT_FLOW_TIMEOUT_SECONDS: int = 30 * 60
    AGENT_PI_TOOL_LOOP_MAX_ITERATIONS: int = 30
    # Reasoning models spend completion tokens on hidden reasoning before the JSON
    # action, so the controller budget must stay generous to avoid truncated JSON.
    AGENT_PI_TOOL_LOOP_MAX_TOKENS: int = 16384

    # Web search (for research tasks; DuckDuckGo, free, no API key)
    WEB_SEARCH_ENABLED: bool = True
    WEB_SEARCH_MAX_RESULTS: int = 8

    # App
    APP_URL: str = "http://localhost:3010"
    AUTO_SEED_DATA: bool = False

    TELEMETRY_DISABLED: bool = True
    SUPPORTED_PROVIDER_TYPES: str = "openai_compatible,anthropic_compatible"

    # Optional seed admin bootstrap (used by seed.py)
    SEED_ADMIN_EMAIL: str = ""
    SEED_ADMIN_PASSWORD: str = ""
    SEED_ADMIN_NICKNAME: str = "Administrator"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
