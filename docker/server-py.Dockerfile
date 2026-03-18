FROM mirror.gcr.io/library/python:3.12-slim

WORKDIR /app

# Install system dependencies for building packages
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

# Copy pyproject.toml first for dependency caching
COPY apps/server-py/pyproject.toml .

# Install dependencies only (not the project itself)
RUN uv pip install --system --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "sqlalchemy[asyncio]>=2.0.36" \
    "asyncpg>=0.30.0" \
    "alembic>=1.14.0" \
    "pydantic[email]>=2.10.0" \
    "pydantic-settings>=2.6.0" \
    "redis[hiredis]>=5.2.0" \
    "passlib[bcrypt]>=1.7.4" \
    "python-jose[cryptography]>=3.3.0" \
    "python-multipart>=0.0.12" \
    "graphiti-core==0.28.1" \
    "kuzu>=0.11.3" \
    "openai>=1.55.0" \
    "anthropic>=0.39.0" \
    "httpx>=0.28.0" \
    "sse-starlette>=2.1.0" \
    "python-docx>=1.1.0" \
    "PyPDF2>=3.0.0" \
    || echo "Some deps failed, continuing..."

# Copy full source
COPY apps/server-py/ .

EXPOSE 4000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4000"]
