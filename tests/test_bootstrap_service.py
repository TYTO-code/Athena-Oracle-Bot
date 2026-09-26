"""Bootstrap do primeiro Administrador — RN-008."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from oraculo.db.models import Membro, RegistroAuditoria
from oraculo.domain.hierarchy import VETERANO, CargoInstitucional
from oraculo.services.bootstrap_service import (
    AdministradorJaExisteError,
    promover_primeiro_administrador,
)

ADMINISTRADOR = CargoInstitucional.ADMINISTRADOR


async def test_promove_discord_id_novo_a_administrador(session):
    membro = await promover_primeiro_administrador(session, discord_id=42, nome="Fundador")

    assert membro.administrador is True
    assert membro.discord_id == 42
    assert membro.nome_exibicao == "Fundador"


async def test_promove_membro_ja_existente(session, criar_membro):
    membro = await criar_membro(VETERANO, xp=2_000)

    promovido = await promover_primeiro_administrador(session, discord_id=membro.discord_id)

    assert promovido.id == membro.id
    assert promovido.administrador is True
    assert promovido.patente_slug == VETERANO.slug, "patente não muda com cargo institucional"


async def test_recusa_se_ja_existe_administrador_ativo(session, criar_membro):
    admin = await criar_membro(ADMINISTRADOR)

    with pytest.raises(AdministradorJaExisteError):
        await promover_primeiro_administrador(session, discord_id=999)

    # Ninguém novo foi promovido, e o administrador existente segue intacto.
    novo = await session.scalar(select(Membro).where(Membro.discord_id == 999))
    assert novo is None
    intacto = await session.scalar(select(Membro).where(Membro.id == admin.id))
    assert intacto.administrador is True


async def test_administrador_inativo_nao_bloqueia_bootstrap(session, criar_membro):
    admin_inativo = await criar_membro(ADMINISTRADOR)
    admin_inativo.ativo = False
    await session.flush()

    membro = await promover_primeiro_administrador(session, discord_id=7)

    assert membro.administrador is True


async def test_bootstrap_fica_registrado_na_auditoria(session):
    await promover_primeiro_administrador(session, discord_id=42, nome="Fundador")

    registro = await session.scalar(
        select(RegistroAuditoria).where(
            RegistroAuditoria.acao == "cargo_institucional.concedido"
        )
    )
    assert registro is not None
    assert registro.dados["cargo"] == ADMINISTRADOR.value
    assert registro.ator_descricao == "bootstrap (promover-admin)"
