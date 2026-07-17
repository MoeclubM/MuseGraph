FROM mirror.gcr.io/library/python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=60 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /build

COPY --from=docker.io/astral/uv:0.11.29 /uv /uvx /bin/

COPY apps/server-py/pyproject.toml apps/server-py/pyproject.toml
COPY apps/server-py/uv.lock apps/server-py/uv.lock

WORKDIR /build/apps/server-py

RUN uv venv /app/.venv \
    && uv pip install --python /app/.venv/bin/python "setuptools>=40.8.0" \
    && uv sync --frozen --no-dev --no-install-project --no-build-isolation-package langdetect \
    && uv pip uninstall --python /app/.venv/bin/python setuptools

FROM mirror.gcr.io/library/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY apps/server-py/app /app/app
COPY apps/server-py/alembic.ini /app/alembic.ini
COPY apps/server-py/alembic /app/alembic
COPY apps/server-py/seed.py /app/seed.py

EXPOSE 4000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4000", "--timeout-keep-alive", "600"]
