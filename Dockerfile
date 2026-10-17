# syntax=docker/dockerfile:1

# ── Front end ────────────────────────────────────────────────────────────────
FROM node:25-slim AS web
WORKDIR /web
RUN npm install -g pnpm@11.5.1
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

# ── Backend ──────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS app
# ffmpeg decodes and encodes; rubberband-cli is the good time-stretcher (the
# librosa fallback smears the kick).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg rubberband-cli \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/playlist ./playlist
RUN uv sync --locked --no-dev
COPY --from=web /web/dist /app/web

# State (analysis cache, rendered mixes) on a volume: Mace's root is read-only.
ENV PATH=/app/.venv/bin:$PATH \
    PLAYLIST_DATA_DIR=/data \
    PLAYLIST_WEB_DIST=/app/web \
    NUMBA_CACHE_DIR=/tmp/numba
VOLUME ["/data"]
EXPOSE 8000 8001
USER 1000:1000
CMD ["playlist", "serve", "--port", "8000", "--mcp-port", "8001"]
