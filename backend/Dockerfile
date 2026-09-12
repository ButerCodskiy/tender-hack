FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd -r appgroup && useradd -r -m -g appgroup -s /bin/bash appuser

ENV HF_HOME=/home/appuser/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/appuser/.cache/huggingface \
    TORCH_HOME=/home/appuser/.cache/torch

RUN mkdir -p /data/kb_documents /home/appuser/.cache && chown -R appuser:appgroup /data /home/appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --chown=appuser:appgroup . .

USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
