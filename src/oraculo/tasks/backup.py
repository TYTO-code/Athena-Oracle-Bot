"""Backup automático diário — RNF-005 / US-402.

Suporta os dois bancos do ADR-001:

* **PostgreSQL** — `pg_dump` no formato custom (restaurável com `pg_restore`);
* **SQLite** — cópia consistente via `VACUUM INTO`.

O job roda dentro do próprio processo para não exigir agendador externo em
Render/Railway, e registra cada execução no log de auditoria (RNF-004).
"""

from __future__ import annotations

import asyncio
import os
import shutil
from datetime import timedelta
from pathlib import Path

from sqlalchemy import text

from oraculo.config import Settings, get_settings
from oraculo.db.base import agora, get_engine, sessao
from oraculo.db.models import OrigemAcao
from oraculo.logging_config import get_logger
from oraculo.repositories import auditoria

log = get_logger(__name__)


async def executar_backup(settings: Settings | None = None) -> Path:
    """Gera um arquivo de backup e remove os expirados. Retorna o arquivo criado."""
    cfg = settings or get_settings()
    # Job diário: o custo de I/O síncrono aqui é irrelevante para o event loop.
    destino = Path(cfg.backup_dir).expanduser()  # noqa: ASYNC240
    destino.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
    carimbo = agora().strftime("%Y%m%dT%H%M%SZ")

    if cfg.database_url.startswith("sqlite"):
        arquivo = destino / f"oraculo-{carimbo}.sqlite3"
        await _backup_sqlite(arquivo)
    else:
        arquivo = destino / f"oraculo-{carimbo}.dump"
        await _backup_postgres(cfg, arquivo)

    removidos = _limpar_antigos(destino, cfg.backup_retention_days)
    tamanho = arquivo.stat().st_size if arquivo.exists() else 0

    async with sessao(cfg) as session:
        await auditoria.registrar(
            session,
            acao="backup.executado",
            resumo=f"Backup gerado: {arquivo.name} ({tamanho} bytes)",
            alvo_tipo="backup",
            alvo_id=arquivo.name,
            dados={"bytes": tamanho, "removidos": removidos},
            origem=OrigemAcao.SISTEMA,
        )

    log.info("Backup concluído: %s (%d bytes, %d antigos removidos)", arquivo, tamanho, removidos)
    return arquivo


async def _backup_sqlite(arquivo: Path) -> None:
    """`VACUUM INTO` produz uma cópia íntegra mesmo com escritas em andamento."""
    engine = get_engine()
    async with engine.connect() as conexao:
        await conexao.execute(text("VACUUM INTO :destino"), {"destino": str(arquivo)})


async def _backup_postgres(cfg: Settings, arquivo: Path) -> None:
    if shutil.which("pg_dump") is None:
        raise RuntimeError("pg_dump não encontrado no PATH; instale o cliente PostgreSQL.")

    # `pg_dump` não entende o driver asyncpg na URL.
    url = cfg.database_url.replace("+asyncpg", "")
    processo = await asyncio.create_subprocess_exec(
        "pg_dump",
        "--format=custom",
        f"--file={arquivo}",
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PGCONNECT_TIMEOUT": "10"},
    )
    _, erro = await processo.communicate()
    if processo.returncode != 0:
        detalhe = erro.decode(errors="replace")
        raise RuntimeError(f"pg_dump falhou ({processo.returncode}): {detalhe}")


def _limpar_antigos(destino: Path, dias: int) -> int:
    """Aplica a política de retenção; nunca apaga o backup mais recente."""
    limite = agora() - timedelta(days=dias)
    arquivos = sorted(
        (p for p in destino.glob("oraculo-*") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removidos = 0
    for arquivo in arquivos[1:]:
        modificado_em = agora().fromtimestamp(arquivo.stat().st_mtime, tz=limite.tzinfo)
        if modificado_em < limite:
            arquivo.unlink(missing_ok=True)
            removidos += 1
    return removidos


async def loop_backup(settings: Settings | None = None) -> None:
    """Executa o backup uma vez por dia no horário configurado (UTC)."""
    cfg = settings or get_settings()
    while True:
        espera = _segundos_ate_proxima_execucao(cfg)
        log.info("Próximo backup em %.1f h.", espera / 3600)
        await asyncio.sleep(espera)
        try:
            await executar_backup(cfg)
        except Exception:  # noqa: BLE001 — falha de backup não derruba o bot
            log.exception("Falha ao executar backup automático")


def _segundos_ate_proxima_execucao(cfg: Settings) -> float:
    agora_utc = agora()
    alvo = agora_utc.replace(hour=cfg.backup_hour_utc % 24, minute=0, second=0, microsecond=0)
    if alvo <= agora_utc:
        alvo += timedelta(days=1)
    return (alvo - agora_utc).total_seconds()
