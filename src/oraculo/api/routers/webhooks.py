"""Webhooks externos — TD-003 / US-102 / RF-012.

Fluxo obrigatório de todo webhook:

1. ler o corpo **bruto** e validar a assinatura HMAC (nada é parseado antes);
2. deduplicar por `event_id` (proteção contra replay);
3. persistir o payload e registrar em auditoria.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from oraculo.api.security import validar_assinatura
from oraculo.config import get_settings
from oraculo.db.base import sessao
from oraculo.db.models import EventoWebhook, OrigemAcao
from oraculo.domain.errors import AssinaturaInvalidaError
from oraculo.logging_config import get_logger
from oraculo.repositories import auditoria

log = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

ORIGEM_CLICKUP = "clickup"


@router.post("/clickup", status_code=status.HTTP_202_ACCEPTED, summary="Webhook do ClickUp")
async def clickup(
    request: Request,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
    x_signature_timestamp: str | None = Header(default=None, alias="X-Signature-Timestamp"),
) -> dict:
    cfg = get_settings()
    corpo = await request.body()

    try:
        validar_assinatura(
            corpo=corpo,
            assinatura_recebida=x_signature,
            segredo=cfg.clickup_webhook_secret,
            timestamp=x_signature_timestamp,
            tolerancia_segundos=cfg.webhook_max_skew_seconds,
        )
    except AssinaturaInvalidaError as exc:
        log.warning("Webhook ClickUp rejeitado: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        payload = json.loads(corpo or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Payload não é JSON válido."
        ) from exc

    evento_id = str(
        payload.get("webhook_id")
        or payload.get("event_id")
        or request.headers.get("X-Request-Id")
        or ""
    )
    tipo_evento = payload.get("event")

    async with sessao() as session:
        if evento_id:
            ja_existe = await session.scalar(
                select(EventoWebhook.id).where(
                    EventoWebhook.origem == ORIGEM_CLICKUP,
                    EventoWebhook.evento_id == evento_id,
                )
            )
            if ja_existe:
                log.info("Webhook %s já processado; ignorando replay.", evento_id)
                return {"status": "duplicado", "evento_id": evento_id}

        registro = EventoWebhook(
            origem=ORIGEM_CLICKUP,
            evento_id=evento_id or f"sem-id-{id(corpo)}",
            tipo_evento=tipo_evento,
            payload=payload,
            processado=True,
        )
        session.add(registro)

        await auditoria.registrar(
            session,
            acao="webhook.recebido",
            resumo=f"ClickUp: {tipo_evento or 'evento sem tipo'}",
            alvo_tipo="webhook",
            alvo_id=evento_id or None,
            dados={"tipo": tipo_evento},
            origem=OrigemAcao.API,
        )

    return {"status": "aceito", "evento_id": evento_id, "tipo": tipo_evento}
