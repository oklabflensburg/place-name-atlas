FROM ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv
FROM python:3.13.15-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends gdal-bin ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV PYTHONPATH=/app/apps/api UV_PROJECT_ENVIRONMENT=/app/.venv UV_NO_CACHE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY apps/api apps/api
COPY alembic.ini .
COPY tests/fixtures tests/fixtures
RUN useradd --uid 10001 --create-home atlas
USER atlas
CMD ["uv", "run", "--no-sync", "uvicorn", "atlas.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--h11-max-incomplete-event-size", "65536"]
