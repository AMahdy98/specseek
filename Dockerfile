# syntax=docker/dockerfile:1

# ---- Stage 1: builder — resolve and install dependencies into /app/.venv ----
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency manifests first, source code later: this layer (the slow one) is rebuilt only
# when pyproject.toml/uv.lock change, not on every code edit.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# ---- Stage 2: runtime — only the venv and the code, no uv, no build cache ----
FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 1000 app
WORKDIR /app

# Same path as in the builder: venv scripts contain absolute paths.
COPY --from=builder /app/.venv /app/.venv
COPY app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8080

# Cloud Run injects $PORT. `exec` replaces the shell, so uvicorn is PID 1 and receives SIGTERM.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
