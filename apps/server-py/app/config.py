from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://musegraph:musegraph123@localhost:5432/musegraph"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    TASK_STATE_SQLITE_PATH: str = ".musegraph/task_state.sqlite3"

    # Session
    SESSION_EXPIRES_HOURS: int = 168  # 7 days

    # File storage (local persistent path)
    FILE_STORAGE_ROOT: str = ".musegraph/storage"

    # Optional Neo4j config and local Graphiti store path
    NEO4J_URL: str = ""
    NEO4J_USERNAME: str = ""
    NEO4J_PASSWORD: str = ""
    NEO4J_DATABASE: str = ""
    GRAPHITI_DB_PATH: str = ".musegraph/graphiti/graphiti.kuzu"
    GRAPHITI_EMBEDDING_DIM: int = 1024

    # App
    APP_URL: str = "http://localhost:3010"
    AUTO_SEED_DATA: bool = False

    TELEMETRY_DISABLED: bool = True
    GRAPH_BACKEND: str = "graphiti"
    SUPPORTED_PROVIDER_TYPES: str = "openai_compatible,anthropic_compatible"

    # Optional seed admin bootstrap (used by seed.py)
    SEED_ADMIN_EMAIL: str = ""
    SEED_ADMIN_PASSWORD: str = ""
    SEED_ADMIN_NICKNAME: str = "Administrator"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
