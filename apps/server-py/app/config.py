from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://musegraph:musegraph123@localhost:5432/musegraph"
    COGNEE_DATABASE_URL: str = ""

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    TASK_STATE_SQLITE_PATH: str = ".musegraph/task_state.sqlite3"

    # Session
    SESSION_EXPIRES_HOURS: int = 168  # 7 days

    # File storage (local persistent path)
    FILE_STORAGE_ROOT: str = ".musegraph/storage"

    # AI
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    LLM_API_KEY: str = ""
    LLM_ENDPOINT: str = ""
    LLM_MODEL: str = ""

    # Cognee LLM (defaults to OPENAI_API_KEY if not set)
    COGNEE_LLM_API_KEY: str = ""
    COGNEE_LLM_BASE_URL: str = ""
    COGNEE_LLM_MODEL: str = ""

    # Cognee / Neo4j
    NEO4J_URL: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = "musegraph123"

    # App
    APP_URL: str = "http://localhost:3000"
    AUTO_SEED_DATA: bool = False

    TELEMETRY_DISABLED: bool = True
    # Optional bootstrap for default provider/model/pricing
    AUTO_BOOTSTRAP_NEWAPI: bool = False
    NEWAPI_PROVIDER_NAME: str = "NewAPI"
    NEWAPI_PROVIDER_TYPE: str = "openai_compatible"
    SUPPORTED_PROVIDER_TYPES: str = "openai_compatible,anthropic_compatible"
    NEWAPI_PROVIDER_PRIORITY: int = 100
    NEWAPI_BASE_URL: str = ""
    NEWAPI_API_KEY: str = ""
    NEWAPI_MODEL: str = ""
    NEWAPI_INPUT_PRICE: float = 0.0011
    NEWAPI_OUTPUT_PRICE: float = 0.0044

    # Optional seed admin bootstrap (used by seed.py)
    SEED_ADMIN_EMAIL: str = ""
    SEED_ADMIN_PASSWORD: str = ""
    SEED_ADMIN_NICKNAME: str = "Administrator"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
