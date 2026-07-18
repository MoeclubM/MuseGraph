from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://musegraph:musegraph123@localhost:5432/musegraph"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    # Session
    SESSION_EXPIRES_HOURS: int = 168  # 7 days
    SESSION_COOKIE_NAME: str = "musegraph_session"
    COOKIE_SECURE: bool = False
    REGISTRATION_MODE: str = "disabled"
    SECRET_ENCRYPTION_KEY: str = ""

    # File storage (local persistent path)
    FILE_STORAGE_ROOT: str = ".musegraph/storage"

    # Cognee backend (project memory + vector + graph)
    COGNEE_DATA_DIR: str = ".musegraph/cognee"
    COGNEE_LLM_MAX_TOKENS: int = 8192
    MEMORY_SERVICE_URL: str = "http://memory:4010"
    INTERNAL_SERVICE_TOKEN: str = ""

    # Agent
    AGENT_PI_TOOL_LOOP_MAX_TOKENS: int = 16384
    AGENT_WORKER_ID: str = ""
    AGENT_WORKER_LEASE_SECONDS: int = 60

    MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024
    ALLOW_PRIVATE_PROVIDER_URLS: bool = False
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10
    UPLOAD_RATE_LIMIT_PER_MINUTE: int = 20
    AGENT_RATE_LIMIT_PER_MINUTE: int = 30

    # App
    APP_ENV: str = "development"
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
