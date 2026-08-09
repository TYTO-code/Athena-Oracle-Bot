"""Validação de assinatura de webhooks — TD-003 / RNF-003 / US-102.

O endpoint do legado aceitava qualquer payload, permitindo injeção de dados
falsos. Aqui todo webhook é verificado com HMAC-SHA256 sobre o corpo **bruto**
(antes de qualquer parsing) e comparado em tempo constante.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from oraculo.domain.errors import AssinaturaInvalidaError
from oraculo.logging_config import get_logger

log = get_logger(__name__)

HEADER_ASSINATURA = "X-Signature"
HEADER_TIMESTAMP = "X-Signature-Timestamp"


def assinar(corpo: bytes, segredo: str) -> str:
    """Assinatura hexadecimal esperada para `corpo` — usada também nos testes."""
    return hmac.new(segredo.encode("utf-8"), corpo, hashlib.sha256).hexdigest()


def validar_assinatura(
    *,
    corpo: bytes,
    assinatura_recebida: str | None,
    segredo: str | None,
    timestamp: str | None = None,
    tolerancia_segundos: int = 300,
) -> None:
    """Levanta `AssinaturaInvalidaError` se o webhook não for autêntico.

    Sem segredo configurado a requisição é **rejeitada**: falhar fechado é o
    comportamento correto para um endpoint que grava dados (RNF-003).
    """
    if not segredo:
        log.error("Webhook recebido sem ORACULO_CLICKUP_WEBHOOK_SECRET configurado.")
        raise AssinaturaInvalidaError("segredo de webhook não configurado no servidor")

    if not assinatura_recebida:
        raise AssinaturaInvalidaError(f"header {HEADER_ASSINATURA} ausente")

    # Replay: só é verificado quando a origem envia timestamp.
    if timestamp is not None:
        try:
            enviado_em = float(timestamp)
        except ValueError as exc:
            raise AssinaturaInvalidaError("timestamp inválido") from exc
        if abs(time.time() - enviado_em) > tolerancia_segundos:
            raise AssinaturaInvalidaError("timestamp fora da janela de tolerância")

    esperada = assinar(corpo, segredo)
    recebida = assinatura_recebida.strip()
    # Aceita tanto `abc123` quanto `sha256=abc123`.
    if "=" in recebida:
        recebida = recebida.split("=", 1)[1]

    if not hmac.compare_digest(esperada, recebida):
        raise AssinaturaInvalidaError("assinatura HMAC-SHA256 não confere")
