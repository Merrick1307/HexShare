FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.1.4 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && pip install --no-cache-dir "poetry==${POETRY_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fontconfig \
        fonts-dejavu-core \
        fonts-liberation2 \
        fonts-noto-core \
    && groupadd --system hexshare \
    && useradd --system --gid hexshare --create-home --home-dir /home/hexshare hexshare \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder --chown=hexshare:hexshare /app/.venv /app/.venv
COPY --chown=hexshare:hexshare app ./app
COPY --chown=hexshare:hexshare migrations ./migrations
COPY --chown=hexshare:hexshare run_migrations.py ./run_migrations.py
COPY --chown=hexshare:hexshare entrypoint.sh ./entrypoint.sh

RUN chmod 0555 /app/entrypoint.sh

USER hexshare

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
