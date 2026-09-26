"""Sincronização Google Agenda → bot — US-305 (sentido que faltava).

O bot já espelha no Google o que é criado, alterado e cancelado por comando.
Este job cobre o caminho de volta: a cada `google_sync_intervalo_minutos`,
busca no calendário os eventos alterados desde a última leitura (inclusive os
apagados) e aplica em `AgendaService.aplicar_alteracoes_externas`.

O cursor fica em memória: depois de um restart, relê as últimas 24 h. Não há
risco nisso porque aplicar a mesma alteração de novo não muda nada.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from oraculo.config import Settings, get_settings
from oraculo.db.base import agora, sessao
from oraculo.integrations.google_calendar import AgendaExterna, criar_agenda_externa
from oraculo.logging_config import get_logger
from oraculo.services.agenda_service import AgendaService, ResumoSincronizacaoExterna

log = get_logger(__name__)

JANELA_INICIAL = timedelta(hours=24)
#: Sobreposição entre leituras: um evento alterado no exato instante da leitura
#: anterior não pode escapar por diferença de relógio.
SOBREPOSICAO = timedelta(minutes=1)


async def sincronizar_agenda_uma_vez(
    desde: datetime,
    *,
    externa: AgendaExterna,
    settings: Settings | None = None,
) -> ResumoSincronizacaoExterna:
    alteracoes = await externa.alteracoes_desde(desde)
    async with sessao(settings) as session:
        resumo = await AgendaService(agenda_externa=externa).aplicar_alteracoes_externas(
            session, alteracoes
        )
    if resumo.atualizados or resumo.cancelados:
        log.info(
            "Google → bot: %d atualizados, %d cancelados, %d ignorados.",
            resumo.atualizados,
            resumo.cancelados,
            resumo.ignorados,
        )
    return resumo


async def loop_agenda_google(settings: Settings | None = None) -> None:
    """Roda para sempre; uma falha do Google não derruba o bot, só espera o próximo ciclo."""
    cfg = settings or get_settings()
    intervalo = max(1.0, cfg.google_sync_intervalo_minutos) * 60
    externa = criar_agenda_externa(cfg)
    cursor = agora() - JANELA_INICIAL

    while True:
        inicio_leitura = agora()
        try:
            await sincronizar_agenda_uma_vez(cursor, externa=externa, settings=cfg)
            cursor = inicio_leitura - SOBREPOSICAO
        except Exception:  # noqa: BLE001 — integração externa não derruba o bot
            log.exception("Falha ao sincronizar alterações do Google Agenda")
        await asyncio.sleep(intervalo)
