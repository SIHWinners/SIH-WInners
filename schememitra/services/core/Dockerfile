# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

COPY services/core/pyproject.toml services/core/uv.lock ./
RUN uv sync --frozen --no-dev --extra queue --extra s3 --no-install-project

COPY services/core/ ./
COPY packages/i18n /packages/i18n
ENV PATH="/app/.venv/bin:$PATH" I18N_DIR=/packages/i18n

RUN useradd --system --uid 10001 app && mkdir -p /app/var && chown -R app /app/var
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
