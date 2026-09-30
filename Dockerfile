FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY server ./server
COPY plugins/youtube-lecture/resources/lecture-v1.schema.json ./plugins/youtube-lecture/resources/lecture-v1.schema.json

ENV PYTHONUNBUFFERED=1
CMD ["sh", "-c", "uv run --no-dev uvicorn server.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
