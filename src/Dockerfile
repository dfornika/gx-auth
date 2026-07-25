# syntax=docker/dockerfile:1
# Mirrors gx-core: uv-managed venv kept OUTSIDE /src so the compose bind mount
# does not shadow it.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /src

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for layer caching.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-editable

COPY . /src/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable

# Collect static assets into STATIC_ROOT (whitenoise serves them in prod).
# Dummy DB/secret so settings import cleanly at build time.
RUN DATABASE_URL=sqlite://:memory: SECRET_KEY=build-only-key \
    uv run -m manage collectstatic --noinput

EXPOSE 8000

# Dev default; production (Fargate) overrides this with gunicorn (see infrastructure/).
CMD ["uv", "run", "-m", "manage", "runserver", "0.0.0.0:8000"]
