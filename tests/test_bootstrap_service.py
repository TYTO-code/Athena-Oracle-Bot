"""Bootstrap do primeiro Administrador — RN-008."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from oraculo.db.models import Membro, RegistroAuditoria
from oraculo.domain.hierarchy import ADMINISTRADOR, CAVALARIA, MEMBRO
from oraculo.services.bootstrap_service import (
    AdministradorJaExisteError,
    promover_primeiro_administrador,
)


async def test_promove_discord_id_novo_a_administrador(session):
    membro = await promover_primeiro_administrador(session, discord_id=42, nome="Fundador")

    assert membro.cargo_slug == ADMINISTRADOR.slug
    assert membro.discord_id == 42
    assert membro.nome_exibicao == "Fundador"


async def test_promove_membro_ja_existente(session, criar_membro):
    membro = await criar_membro(CAVALARIA, xp=600)

    promovido = await promover_primeiro_administrador(session, discord_id=membro.discord_id)

    assert promovido.id == membro.id
    assert promovido.cargo_slug == ADMINISTRADOR.slug


async def test_recusa_se_ja_existe_administrador_ativo(session, criar_membro):
    admin = await criar_membro(ADMINISTRADOR)

    with pytest.raises(AdministradorJaExisteError):
        await promover_primeiro_administrador(session, discord_id=999)

    # Ninguém novo foi promovido, e o administrador existente segue intacto.
    novo = await session.scalar(select(Membro).where(Membro.discord_id == 999))
    assert novo is None
    intacto = await session.scalar(select(Membro).where(Membro.id == admin.id))
    assert intacto.cargo_slug == ADMINISTRADOR.slug


async def test_administrador_inativo_nao_bloqueia_bootstrap(session, criar_membro):
    admin_inativo = await criar_membro(ADMINISTRADOR)
    admin_inativo.ativo = False
    await session.flush()

    membro = await promover_primeiro_administrador(session, discord_id=7)

    assert membro.cargo_slug == ADMINISTRADOR.slug


async def test_bootstrap_fica_registrado_na_auditoria(session):
    await promover_primeiro_administrador(session, discord_id=42, nome="Fundador")

    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "promocao.aplicada")
    )
    assert registro is not None
    assert registro.dados["cargo_novo"] == ADMINISTRADOR.slug


async def test_membro_recem_criado_nasce_no_cargo_inicial_antes_da_promocao(session):
    """A promoção passa pelo histórico normal, não nasce com o cargo pronto (RN-003)."""
    membro = await promover_primeiro_administrador(session, discord_id=42)

    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "promocao.aplicada")
    )
    assert registro.dados["cargo_anterior"] == MEMBRO.slug
    assert membro.cargo_slug == ADMINISTRADOR.slug
