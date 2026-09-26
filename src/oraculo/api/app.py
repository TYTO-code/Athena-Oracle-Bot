"""Aplicação FastAPI — ADR-001 / US-403.

Expõe apenas health check, webhooks assinados e o painel de métricas agregadas
(protegido por token). Não há endpoint público de leitura ou escrita de XP:
toda operação de domínio passa pelo bot, onde a política de permissões (RN-008)
é aplicada com identidade conhecida.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from oraculo import __version__
from oraculo.api.routers import health, metricas, webhooks
from oraculo.config import Settings, get_settings
from oraculo.db.base import criar_schema, encerrar_engine
from oraculo.logging_config import get_logger, setup_logging

log = get_logger(__name__)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    cfg: Settings = app.state.settings
    setup_logging(cfg.log_level)

    if not cfg.is_production:
        # Em produção o schema vem de `alembic upgrade head`.
        await criar_schema(cfg)

    pendencias = cfg.validate_for_production()
    if pendencias:
        nivel = log.error if cfg.is_production else log.warning
        for pendencia in pendencias:
            nivel("Pendência de configuração: %s", pendencia)
        if cfg.is_production:
            raise RuntimeError(
                "Configuração inválida para produção (RNF-003): " + "; ".join(pendencias)
            )

    log.info("API pronta em %s:%s", cfg.api_host, cfg.api_port)
    try:
        yield
    finally:
        await encerrar_engine()


def criar_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    app = FastAPI(
        title="Bot Oráculo — API",
        description="Health check e webhooks do Bot Oráculo (Clube TYTO / Atena v1.0).",
        version=__version__,
        lifespan=ciclo_de_vida,
        # Documentação interativa desabilitada em produção (RNF-003).
        docs_url=None if cfg.is_production else "/docs",
        redoc_url=None,
    )
    app.state.settings = cfg
    app.include_router(health.router)
    app.include_router(webhooks.router)
    app.include_router(metricas.router)
    return app


app = criar_app()
