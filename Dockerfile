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

# ---- Stage 2: ui — compile the React app to static files (HTML, JS, CSS) ----
FROM node:24-slim AS ui
WORKDIR /ui
# Same trick as above: manifests first, so `npm ci` is cached until dependencies change.
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
# Empty API URL: the UI calls /v1/... on whatever host served the page (same origin).
RUN VITE_API_URL= npm run build

# ---- Stage 3: runtime — only the venv, the code and the built UI; no uv, no Node ----
FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 1000 app
WORKDIR /app

# Same path as in the builder: venv scripts contain absolute paths.
COPY --from=builder /app/.venv /app/.venv
COPY app ./app
COPY --from=ui /ui/dist ./static

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    STATIC_DIR=/app/static

USER app
EXPOSE 8080

# Cloud Run injects $PORT. `exec` replaces the shell, so uvicorn is PID 1 and receives SIGTERM.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
