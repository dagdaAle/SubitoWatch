FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    SUBITO_DB=/data/subito.db
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/app ./app
COPY backend/alembic ./alembic
# Coolify's CMD healthcheck runs this exact path.
COPY backend/healthcheck.py ./healthcheck.py
COPY --from=frontend /backend/app/static ./app/static
RUN mkdir -p /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "/app/healthcheck.py"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
