FROM ghcr.io/astral-sh/uv:0.12.3 AS uv

FROM python:3.12-slim-bookworm

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_HTTP_TIMEOUT=300
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/api apps/api
COPY apps/worker apps/worker
RUN --mount=type=cache,id=trade-workbench-uv-cache,target=/root/.cache/uv \
    uv sync --frozen --package trade-workbench-worker --no-dev

WORKDIR /app/apps/worker

CMD ["celery", "-A", "worker.app", "--quiet", "worker", "--loglevel=INFO", "--queues=default"]
