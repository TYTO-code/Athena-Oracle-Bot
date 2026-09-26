"""Cargos institucionais — TD-007 / RN-008 / RN-010 (Carta Art. VIII: eixo independente)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from tests.test_promocao import SincronizadorEspiao

from oraculo.db.models import OrigemAcao, Promocao, RegistroAuditoria
from oraculo.domain.errors import (
    AutorNaoIdentificadoError,
    CargoInstitucionalInalteradoError,
    MotivoObrigatorioError,
    PermissaoNegadaError,
    UltimoAdministradorError,
)
from oraculo.domain.hierarchy import OFICIAL, OMNI, CargoInstitucional
from oraculo.services.cargo_institucional_service import CargoInstitucionalService

CONSELHEIRO = CargoInstitucional.CONSELHEIRO
ADMINISTRADOR = CargoInstitucional.ADMINISTRADOR


async def test_administrador_concede_conselheiro_sem_mexer_na_patente(session, criar_membro):
    espiao = SincronizadorEspiao()
    servico = CargoInstitucionalService(sincronizador=espiao)
    admin = await criar_membro(ADMINISTRADOR)
    alvo = await criar_membro(OFICIAL, xp=106_000)

    resultado = await servico.definir(
        session, membro=alvo, cargo=CONSELHEIRO, ativo=True, motivo="Eleito", autor=admin
    )

    assert alvo.conselheiro is True
    assert alvo.patente_slug == "oficial", "cargo institucional não mexe na patente"
    assert alvo.perfil.descricao() == "Oficial · Conselheiro"
    assert resultado.sincronizado is True
    assert espiao.institucionais == [(alvo.discord_id, "conselheiro", True)]
    assert await session.scalar(select(Promocao)) is None

    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "cargo_institucional.concedido")
    )
    assert registro.ator_id == admin.id
    assert registro.dados["motivo"] == "Eleito"


async def test_revogar_conselheiro(session, criar_membro):
    servico = CargoInstitucionalService()
    admin = await criar_membro(ADMINISTRADOR)
    alvo = await criar_membro(CONSELHEIRO)

    await servico.definir(
        session, membro=alvo, cargo=CONSELHEIRO, ativo=False, motivo="Impeachment", autor=admin
    )

    assert alvo.conselheiro is False
    assert await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "cargo_institucional.revogado")
    )


@pytest.mark.parametrize("autor_posicao", [CONSELHEIRO, OMNI])
async def test_so_administrador_define_cargo(session, criar_membro, autor_posicao):
    """Nem Conselheiro nem a patente mais alta nomeiam cargo — só Administrador."""
    servico = CargoInstitucionalService()
    autor = await criar_membro(autor_posicao)
    alvo = await criar_membro(OFICIAL)

    with pytest.raises(PermissaoNegadaError):
        await servico.definir(
            session, membro=alvo, cargo=CONSELHEIRO, ativo=True, motivo="Tentativa", autor=autor
        )
    assert alvo.conselheiro is False


async def test_operacao_sem_efeito_e_recusada(session, criar_membro):
    servico = CargoInstitucionalService()
    admin = await criar_membro(ADMINISTRADOR)
    alvo = await criar_membro(CONSELHEIRO)

    with pytest.raises(CargoInstitucionalInalteradoError):
        await servico.definir(
            session, membro=alvo, cargo=CONSELHEIRO, ativo=True, motivo="De novo", autor=admin
        )


async def test_motivo_obrigatorio(session, criar_membro):
    servico = CargoInstitucionalService()
    admin = await criar_membro(ADMINISTRADOR)
    alvo = await criar_membro(OFICIAL)

    with pytest.raises(MotivoObrigatorioError):
        await servico.definir(
            session, membro=alvo, cargo=CONSELHEIRO, ativo=True, motivo="  ", autor=admin
        )


async def test_nao_revoga_o_ultimo_administrador(session, criar_membro):
    """Sem nenhum Administrador, ninguém mais consegue nomear um (ciclo fechado)."""
    servico = CargoInstitucionalService()
    admin = await criar_membro(ADMINISTRADOR)

    with pytest.raises(UltimoAdministradorError):
        await servico.definir(
            session, membro=admin, cargo=ADMINISTRADOR, ativo=False, motivo="Saindo", autor=admin
        )
    assert admin.administrador is True

    outro = await criar_membro(ADMINISTRADOR)
    await servico.definir(
        session, membro=admin, cargo=ADMINISTRADOR, ativo=False, motivo="Saindo", autor=outro
    )
    assert admin.administrador is False


async def test_sem_autor_so_como_sistema(session, criar_membro):
    servico = CargoInstitucionalService()
    alvo = await criar_membro(OFICIAL)

    with pytest.raises(AutorNaoIdentificadoError):
        await servico.definir(
            session, membro=alvo, cargo=ADMINISTRADOR, ativo=True, motivo="Sem autor", autor=None
        )

    await servico.definir(
        session,
        membro=alvo,
        cargo=ADMINISTRADOR,
        ativo=True,
        motivo="Bootstrap",
        autor=None,
        origem=OrigemAcao.SISTEMA,
    )
    assert alvo.administrador is True


async def test_falha_no_discord_nao_desfaz_o_cargo(session, criar_membro):
    servico = CargoInstitucionalService(sincronizador=SincronizadorEspiao(falhar=True))
    admin = await criar_membro(ADMINISTRADOR)
    alvo = await criar_membro(OFICIAL)

    resultado = await servico.definir(
        session, membro=alvo, cargo=CONSELHEIRO, ativo=True, motivo="Eleito", autor=admin
    )

    assert alvo.conselheiro is True
    assert resultado.sincronizado is False
    assert "Discord fora do ar" in resultado.erro_sincronizacao
