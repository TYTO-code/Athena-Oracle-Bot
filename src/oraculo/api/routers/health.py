"""Health check e prontidão — US-403 / RNF-001.

`/health` responde sem tocar em dependências (liveness);
`/health/ready` valida banco e cache (readiness), para orquestrador/monitor.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from oraculo import __version__
from oraculo.config import get_settings
from oraculo.db.base import agora, sessao
from oraculo.logging_config import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["observabilidade"])


@router.get("/health", summary="Liveness")
async def health() -> dict:
    cfg = get_settings()
    return {
        "status": "ok",
        "servico": "bot-oraculo",
        "versao": __version__,
        "ambiente": cfg.env,
        "hora": agora().isoformat(),
    }


@router.get("/health/ready", summary="Readiness (banco e cache)")
async def readiness(response: Response) -> dict:
    checagens: dict[str, str] = {}

    try:
        async with sessao() as session:
            await session.execute(text("SELECT 1"))
        checagens["banco"] = "ok"
    except Exception as exc:  # noqa: BLE001 — readiness precisa reportar, não estourar
        log.warning("Readiness: banco indisponível (%s)", exc)
        checagens["banco"] = f"falha: {type(exc).__name__}"

    cfg = get_settings()
    checagens["cache"] = "redis" if cfg.redis_url else "memoria"
    checagens["google_agenda"] = "habilitado" if cfg.google_enabled else "desabilitado"

    pronto = checagens["banco"] == "ok"
    if not pronto:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"pronto": pronto, "checagens": checagens}
