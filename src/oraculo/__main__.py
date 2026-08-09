"""Ponto de entrada do Bot Oráculo.

Um único processo sobe o bot Discord, a API de webhooks/health e o job de
backup, conforme as flags de ambiente. Isso mantém o deploy simples em
Render/Railway (ADR-001) sem impedir a separação futura em serviços distintos
— basta subir o mesmo container com `ORACULO_RUN_BOT`/`ORACULO_RUN_API`.

Uso::

    python -m oraculo              # bot + API conforme o .env
    python -m oraculo bot          # apenas o bot
    python -m oraculo api          # apenas a API
    python -m oraculo db-init      # cria o schema (dev)
    python -m oraculo backup       # executa um backup imediato
    python -m oraculo verificar    # valida a configuração (RNF-003)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys

from oraculo.config import Settings, get_settings
from oraculo.logging_config import get_logger, setup_logging

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Serviços
# ---------------------------------------------------------------------------


async def rodar_bot(cfg: Settings) -> None:
    from oraculo.bot.client import criar_bot
    from oraculo.db.base import criar_schema

    if not cfg.is_production:
        await criar_schema(cfg)

    bot = criar_bot(cfg)
    async with bot:
        await bot.start(cfg.require_discord_token())


async def rodar_api(cfg: Settings) -> None:
    import uvicorn

    from oraculo.api.app import criar_app

    config = uvicorn.Config(
        criar_app(cfg),
        host=cfg.api_host,
        port=cfg.api_port,
        log_level=cfg.log_level.lower(),
        access_log=not cfg.is_production,
    )
    await uvicorn.Server(config).serve()


async def rodar_tudo(cfg: Settings) -> None:
    from oraculo.tasks.backup import loop_backup

    tarefas: list[asyncio.Task] = []
    if cfg.run_bot:
        tarefas.append(asyncio.create_task(rodar_bot(cfg), name="bot"))
    if cfg.run_api:
        tarefas.append(asyncio.create_task(rodar_api(cfg), name="api"))
    if cfg.backup_enabled:
        tarefas.append(asyncio.create_task(loop_backup(cfg), name="backup"))

    if not tarefas:
        log.error("Nada para executar: habilite ORACULO_RUN_BOT e/ou ORACULO_RUN_API.")
        return

    await _aguardar(tarefas)


async def _aguardar(tarefas: list[asyncio.Task]) -> None:
    """Encerra tudo quando a primeira tarefa termina ou chega SIGTERM/SIGINT."""
    parada = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sinal in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):  # Windows
            loop.add_signal_handler(sinal, parada.set)

    espera_parada = asyncio.create_task(parada.wait(), name="parada")
    concluidas, _ = await asyncio.wait(
        [*tarefas, espera_parada], return_when=asyncio.FIRST_COMPLETED
    )

    for tarefa in [*tarefas, espera_parada]:
        if not tarefa.done():
            tarefa.cancel()
    await asyncio.gather(*tarefas, espera_parada, return_exceptions=True)

    for tarefa in concluidas:
        if tarefa is not espera_parada and (erro := tarefa.exception()):
            raise erro
    log.info("Encerrado.")


# ---------------------------------------------------------------------------
# Comandos auxiliares
# ---------------------------------------------------------------------------


async def comando_db_init(cfg: Settings) -> None:
    from oraculo.db.base import criar_schema, encerrar_engine

    await criar_schema(cfg)
    await encerrar_engine()
    print("Schema criado/atualizado.")


async def comando_backup(cfg: Settings) -> None:
    from oraculo.db.base import encerrar_engine
    from oraculo.tasks.backup import executar_backup

    arquivo = await executar_backup(cfg)
    await encerrar_engine()
    print(f"Backup gerado em {arquivo}")


def comando_verificar(cfg: Settings) -> int:
    """RNF-003 — verifica a configuração antes de um deploy."""
    pendencias = cfg.validate_for_production()
    if not pendencias:
        print("Configuração válida para produção. ✅")
        return 0
    print("Pendências de configuração:")
    for pendencia in pendencias:
        print(f"  • {pendencia}")
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="oraculo", description="Bot Oráculo — Clube TYTO")
    parser.add_argument(
        "comando",
        nargs="?",
        default="tudo",
        choices=["tudo", "bot", "api", "db-init", "backup", "verificar"],
        help="O que executar (padrão: tudo, conforme as flags do .env).",
    )
    args = parser.parse_args(argv)

    cfg = get_settings()
    setup_logging(cfg.log_level)

    if args.comando == "verificar":
        return comando_verificar(cfg)

    rotinas = {
        "tudo": rodar_tudo,
        "bot": rodar_bot,
        "api": rodar_api,
        "db-init": comando_db_init,
        "backup": comando_backup,
    }
    try:
        asyncio.run(rotinas[args.comando](cfg))
    except KeyboardInterrupt:  # pragma: no cover
        log.info("Interrompido pelo usuário.")
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
