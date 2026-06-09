FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --group ui --no-install-project

COPY . .
RUN uv sync --locked --group ui

ENV PYTHONPATH=/app:/app/ui
ENV ERGANI_UI_HOST=0.0.0.0
ENV ERGANI_UI_PORT=8080
ENV ERGANI_UI_HTTPS=1

EXPOSE 8080

CMD ["sh", "ui/docker-entrypoint.sh"]
