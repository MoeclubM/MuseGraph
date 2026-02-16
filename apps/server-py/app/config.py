from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://musegraph:musegraph123@localhost:5432/musegraph"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # JWT
    JWT_SECRET: str = "your-super-secret-jwt-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_HOURS: int = 168  # 7 days

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_USE_SSL: bool = False
    MINIO_BUCKET: str = "musegraph"

    # AI
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # Cognee LLM (defaults to OPENAI_API_KEY if not set)
    COGNEE_LLM_API_KEY: str = ""
    COGNEE_LLM_BASE_URL: str = ""
    COGNEE_LLM_MODEL: str = "openai/gpt-4o-mini"

    # Cognee / Neo4j
    NEO4J_URL: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = "musegraph123"

    # App
    APP_URL: str = "http://localhost:3000"
    AUTO_SEED_DATA: bool = False

    # Optional seed admin bootstrap (used by seed.py)
    SEED_ADMIN_EMAIL: str = ""
    SEED_ADMIN_USERNAME: str = ""
    SEED_ADMIN_PASSWORD: str = ""
    SEED_ADMIN_NICKNAME: str = "Administrator"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
