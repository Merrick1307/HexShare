FROM python:3.14-alpine

WORKDIR /app

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock /app/

RUN poetry install --no-root

COPY . .

EXPOSE 8000

CMD ["poetry", "run", "python", "-m", "app.main"]
