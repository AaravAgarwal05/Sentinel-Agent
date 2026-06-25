# Stage 1: builder
FROM python:3.11-slim AS builder

ENV POETRY_VIRTUALENVS_IN_PROJECT=true

RUN pip install --no-cache-dir poetry

WORKDIR /build
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

# Stage 2: runtime
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

RUN groupadd --system sentinel && \
    useradd --system --gid sentinel --no-create-home sentinel && \
    mkdir -p /data && chown sentinel:sentinel /data

WORKDIR /app
COPY agent/ /app/agent/
COPY src/ /app/src/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini

USER sentinel

ENTRYPOINT ["python", "-m", "src.main"]
