"""Engine, sessão e metadata do SQLAlchemy async.

TD-002 — substitui `xp_data.json` / `teams_data.json` por persistência
relacional transacional, eliminando as race conditions do legado.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from oraculo.config import Settings, get_settings
from oraculo.logging_config import get_logger

log = get_logger(__name__)

# Convenção de nomes: migrações Alembic previsíveis em Postgres e SQLite.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa de todos os modelos."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def agora() -> datetime:
    """Timestamp único do sistema: sempre UTC e timezone-aware (RN-005)."""
    return datetime.now(UTC)


def como_utc(momento: datetime) -> datetime:
    """Datetime lido do banco, garantidamente timezone-aware.

    SQLite não guarda o fuso: a mesma coluna `DateTime(timezone=True)` volta
    *naive* de lá e *aware* do PostgreSQL. Como tudo é gravado em UTC por
    `agora()`, o naive é UTC — esta função diz isso em voz alta, em vez de
    deixar a comparação estourar só no ambiente de desenvolvimento.
    """
    return momento if momento.tzinfo is not None else momento.replace(tzinfo=UTC)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _preparar_sqlite(url: str) -> None:
    """Garante o diretório do arquivo SQLite antes de abrir a conexão."""
    if not url.startswith("sqlite"):
        return
    _, _, caminho = url.partition("///")
    caminho = caminho.split("?", 1)[0]
    if caminho and caminho != ":memory:":
        Path(caminho).expanduser().parent.mkdir(parents=True, exist_ok=True)


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Engine assíncrona única do processo."""
    global _engine
    if _engine is None:
        cfg = settings or get_settings()
        _preparar_sqlite(cfg.database_url)
        kwargs: dict[str, object] = {"echo": cfg.db_echo, "future": True}
        if not cfg.database_url.startswith("sqlite"):
            # Pool dimensionado para picos de comandos (RNF-001 / RNF-002).
            kwargs |= {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}
        _engine = create_async_engine(cfg.database_url, **kwargs)
        log.info("Engine criada para %s", _mascarar(cfg.database_url))
    return _engine


def get_sessionmaker(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """Fábrica de sessões (`expire_on_commit=False` para uso pós-commit)."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(settings),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


@asynccontextmanager
async def sessao(settings: Settings | None = None) -> AsyncIterator[AsyncSession]:
    """Sessão transacional: commit no sucesso, rollback em qualquer erro.

    RN-005 / RN-010 — a movimentação e o respectivo registro de auditoria são
    gravados na **mesma** transação; nunca existe XP alterado sem trilha.
    """
    factory = get_sessionmaker(settings)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def criar_schema(settings: Settings | None = None) -> None:
    """Cria as tabelas a partir dos modelos.

    Conveniência de desenvolvimento e testes. Em produção o schema é aplicado
    por migrações Alembic (`alembic upgrade head`).
    """
    from oraculo.db import models  # noqa: F401 — registra os modelos na metadata

    engine = get_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("Schema garantido (%d tabelas).", len(Base.metadata.tables))


async def encerrar_engine() -> None:
    """Fecha o pool de conexões no shutdown da aplicação."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        log.info("Engine encerrada.")
    _engine = None
    _sessionmaker = None


def _mascarar(url: str) -> str:
    """Oculta credenciais da URL antes de logar (RNF-003)."""
    if "@" not in url:
        return url
    esquema, _, resto = url.partition("://")
    _, _, host = resto.rpartition("@")
    return f"{esquema}://***@{host}"
