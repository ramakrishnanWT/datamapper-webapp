# syntax=docker/dockerfile:1.7
#
# Multi-stage build for Data eXchange Mapper.
#
# Stage 1 (builder): Node 20 + corepack yarn → builds the Kaoto Online
#   SPA from source with our customizations applied.
#
# Stage 2 (runtime): Slim Python image running Flask, serving the built
#   SPA as static assets.

ARG NODE_IMAGE=node:20-bookworm-slim
ARG PYTHON_IMAGE=python:3.12-slim-bookworm

# ----------------------------------------------------------------------------
# Stage 1 — build Kaoto UI
# ----------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS kaoto-builder

ARG KAOTO_REPO=https://github.com/KaotoIO/kaoto
ARG KAOTO_REF=main

ENV VITE_ENABLE_DATAMAPPER_DEBUGGER=true \
    VITE_DATAMAPPER_ONLY=true

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && corepack enable

WORKDIR /build

# Clone Kaoto (shallow).
# Pass --build-arg KAOTO_CACHE_BUST=$(date +%s) to force a fresh clone.
ARG KAOTO_CACHE_BUST=1
RUN git clone --depth 1 --branch "${KAOTO_REF}" "${KAOTO_REPO}" kaoto

# Apply the Data eXchange Mapper patch.
COPY scripts/kaoto.patch /build/kaoto.patch
WORKDIR /build/kaoto
RUN git apply --whitespace=nowarn /build/kaoto.patch \
 && rm /build/kaoto.patch

# Install + build. Cache the yarn store.
RUN --mount=type=cache,target=/root/.yarn,sharing=locked \
    --mount=type=cache,target=/root/.cache/node,sharing=locked \
    corepack yarn install --immutable

RUN corepack yarn workspace '@kaoto/kaoto' build


# ----------------------------------------------------------------------------
# Stage 2 — Python/Flask runtime
# ----------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_PORT=5000 \
    FRONTEND_DIST=/app/dist \
    WORKSPACE_DIR=/app/workspace

# Non-root user
RUN groupadd -r app && useradd -r -g app -d /app -s /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0

COPY app.py ./
COPY sample/ ./sample/
COPY --from=kaoto-builder /build/kaoto/packages/ui/dist /app/dist

RUN mkdir -p /app/workspace /app/data \
 && chown -R app:app /app

USER app

EXPOSE 5000

# Production server (gunicorn) by default; flip CMD to `python app.py`
# for the dev server with hot-reload.
# WEB_CONCURRENCY env var (set in docker-compose.yml) controls worker count.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "60", "app:app"]
