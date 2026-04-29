FROM mirror.gcr.io/library/python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip build hatchling

COPY apps/server-py/pyproject.toml apps/server-py/pyproject.toml
COPY apps/server-py/app apps/server-py/app

RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels ./apps/server-py


FROM mirror.gcr.io/library/python:3.12-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY apps/server-py/seed.py /app/seed.py

RUN python -m pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

EXPOSE 4000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4000"]
