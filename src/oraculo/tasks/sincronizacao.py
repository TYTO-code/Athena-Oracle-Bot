"""Sincronização periódica com a plataforma do clube — RF-001.

Roda dentro do processo do bot, no mesmo padrão do backup: sem agendador
externo, o que mantém o deploy de um container só (ADR-001).

Uma falha de leitura no Firebase **não** derruba o bot nem apaga nada: o job
registra o erro e tenta de novo no próximo ciclo. Quem some da plataforma é
desativado (RN-020), mas uma leitura vazia ou suspeita de ser parcial não
desativa ninguém (ver `ImportacaoService`).
"""

from __future__ import annotations

import asyncio

from oraculo.config import Settings, get_settings
from oraculo.db.base import sessao
from oraculo.integrations.plataforma import criar_fonte_membros
from oraculo.logging_config import get_logger
from oraculo.services.importacao_service import ImportacaoService, Relatorio

log = get_logger(__name__)


def criar_servico_importacao(settings: Settings | None = None) -> ImportacaoService | None:
    """Serviço configurado, ou `None` se a plataforma não estiver habilitada."""
    cfg = settings or get_settings()
    fonte = criar_fonte_membros(cfg)
    if fonte is None:
        return None
    return ImportacaoService(
        fonte,
        mapa_campos=cfg.firebase_campos,
    )


async def sincronizar_uma_vez(settings: Settings | None = None) -> Relatorio | None:
    """Executa uma sincronização completa. Devolve `None` se desabilitada."""
    cfg = settings or get_settings()
    servico = criar_servico_importacao(cfg)
    if servico is None:
        return None

    async with sessao(cfg) as session:
        # RN-020 — quem some da plataforma perde o acesso (soft-delete, RN-010);
        # `importar` ignora a desativação se a leitura vier vazia.
        return await servico.importar(session, desativar_ausentes=True)


async def loop_sincronizacao(settings: Settings | None = None) -> None:
    """Sincroniza no start (se configurado) e depois a cada N horas."""
    cfg = settings or get_settings()
    intervalo = max(0.0, cfg.importacao_intervalo_horas) * 3600

    if cfg.importacao_ao_iniciar:
        await _executar(cfg)

    if intervalo <= 0:
        log.info("Sincronização periódica desligada (intervalo = 0).")
        return

    while True:
        await asyncio.sleep(intervalo)
        await _executar(cfg)


async def _executar(cfg: Settings) -> None:
    try:
        relatorio = await sincronizar_uma_vez(cfg)
    except Exception:  # noqa: BLE001 — integração externa não derruba o bot
        log.exception("Falha na sincronização com a plataforma")
        return
    if relatorio is not None and relatorio.erros:
        log.warning("Sincronização concluída com %d erros.", len(relatorio.erros))
