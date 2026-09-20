"""Bootstrap opcional do Administrador via variável de ambiente — RN-008.

Alternativa a `python -m oraculo promover-admin` para quem só tem acesso ao
painel de variáveis do deploy (sem CLI/espaço local para instalar ferramentas).
"""

from __future__ import annotations

from sqlalchemy import select

from oraculo.__main__ import _bootstrap_admin_se_configurado
from oraculo.db.models import Membro
from oraculo.domain.hierarchy import ADMINISTRADOR


async def test_sem_variavel_nao_faz_nada(session, settings):
    settings.bootstrap_admin_discord_id = None

    await _bootstrap_admin_se_configurado(settings)

    assert await session.scalar(select(Membro)) is None


async def test_promove_via_variavel_de_ambiente(session, settings):
    settings.bootstrap_admin_discord_id = 42

    await _bootstrap_admin_se_configurado(settings)

    membro = await session.scalar(select(Membro).where(Membro.discord_id == 42))
    assert membro is not None
    assert membro.cargo_slug == ADMINISTRADOR.slug


async def test_e_idempotente_se_ja_existe_administrador(session, settings, criar_membro):
    await criar_membro(ADMINISTRADOR)
    settings.bootstrap_admin_discord_id = 42

    await _bootstrap_admin_se_configurado(settings)  # não deve levantar

    assert await session.scalar(select(Membro).where(Membro.discord_id == 42)) is None
