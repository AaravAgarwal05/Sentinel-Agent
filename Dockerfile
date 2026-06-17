# Stage 1: builder
FROM python:3.11-slim AS builder

RUN pip install poetry==2.1.1

WORKDIR /build
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

# Stage 2: runtime
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY agent/ /app/agent/
COPY src/ /app/src/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini

RUN groupadd --system sentinel && \
    useradd --system --gid sentinel --no-create-home sentinel

USER sentinel

ENTRYPOINT ["python", "-m", "src.main"]
