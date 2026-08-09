"""Fixtures compartilhadas.

Os testes rodam sobre SQLite em memória com `StaticPool`, de modo que todas as
conexões enxergam o mesmo banco — o schema testado é exatamente o dos modelos.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from oraculo.config import Settings
from oraculo.db import base as db_base
from oraculo.db.base import Base
from oraculo.db.models import Membro
from oraculo.domain.hierarchy import Cargo


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="development",
        database_url="sqlite+aiosqlite:///:memory:",
        discord_token="token-de-teste",
        clickup_webhook_secret="segredo-de-teste",
        google_enabled=False,
        redis_url=None,
    )


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator:
    motor = create_async_engine(
        settings.database_url, poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with motor.begin() as conexao:
        await conexao.run_sync(Base.metadata.create_all)

    # `sessao()` e os serviços usam os globais do módulo: apontamos para o motor
    # de teste durante o teste e restauramos ao final.
    engine_original, maker_original = db_base._engine, db_base._sessionmaker
    db_base._engine = motor
    db_base._sessionmaker = async_sessionmaker(bind=motor, expire_on_commit=False, autoflush=False)
    try:
        yield motor
    finally:
        db_base._engine, db_base._sessionmaker = engine_original, maker_original
        await motor.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator:
    """Sessão transacional; cada teste começa com o banco limpo."""
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as sessao_teste:
        yield sessao_teste
        await sessao_teste.rollback()


@pytest.fixture
def criar_membro(session):
    """Fábrica de membros persistidos."""
    contador = {"n": 0}

    async def _criar(cargo: Cargo, *, xp: int = 0, nome: str | None = None) -> Membro:
        contador["n"] += 1
        membro = Membro(
            discord_id=1_000_000 + contador["n"],
            nome_exibicao=nome or f"Membro {contador['n']}",
            cargo_slug=cargo.slug,
            xp=xp,
            email=f"membro{contador['n']}@clubetyto.example",
        )
        session.add(membro)
        await session.flush()
        return membro

    return _criar
