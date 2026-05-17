FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation2 \
    fonts-dejavu-core \
    fonts-noto-core \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock /app/

RUN poetry install --no-root

COPY . .

COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
