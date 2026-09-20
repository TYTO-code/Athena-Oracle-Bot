# Bot Oráculo — imagem de execução (ADR-001: Docker + Render/Railway).
# Build em dois estágios para não levar toolchain de compilação para produção.

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .


FROM python:3.12-slim AS runtime

# `postgresql-client` fornece o pg_dump usado pelo backup diário (RNF-005).
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

# Processo sem privilégios de root (RNF-003).
RUN useradd --create-home --uid 10001 oraculo

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ORACULO_API_HOST=0.0.0.0 \
    ORACULO_API_PORT=8000

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY alembic.ini ./
COPY migrations ./migrations
COPY --chown=oraculo:oraculo src ./src
# RN-017 — o regulamento TYTO é lido em runtime por `/perguntar`. Sem esta cópia
# o comando sobe "funcionando", mas sem base de regras nenhuma para responder.
COPY --chown=oraculo:oraculo docs/regras-tyto ./docs/regras-tyto

RUN mkdir -p /app/data /app/backups && chown -R oraculo:oraculo /app
USER oraculo

EXPOSE 8000

# US-403 — o orquestrador reinicia o container se o health check falhar.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:${ORACULO_API_PORT}/health || exit 1

CMD ["python", "-m", "oraculo"]
